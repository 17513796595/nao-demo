import socket
import time
from queue import Queue
import threading
import torch
import os
import struct
import wave
import io

from vad_model import VADModel, is_speech
from asr_model import ASRModel, asr_worker
from qwen_model import QwenModel
from audio_utils import is_valid_text, vad_worker, process_audio_data
from emotion_detector import EmotionDetector
from command_handler import CommandHandler
from aliyun_tts import AliyunTTS  # 导入阿里云TTS

class Server:
    def __init__(self, host="0.0.0.0", audio_port=5000, video_port=5001):
        # 初始化服务器配置
        self.HOST = host
        self.AUDIO_PORT = audio_port
        self.VIDEO_PORT = video_port
        
        # 初始化模型
        self.vad_model = VADModel()  # Silero VAD 模型会自动加载
        self.asr_model = ASRModel()
        self.qwen_model = QwenModel()
        self.command_handler = CommandHandler(nao_ip=host, nao_port=video_port)  # 初始化指令处理器，传入NAO配置
        
        # 初始化情绪检测器（使用固定端口5005作为情绪检测端口）
        self.emotion_detector = EmotionDetector(nao_ip=host, nao_port=video_port, emotion_port=5005)
        
        # 初始化阿里云TTS (新增)
        self.tts = AliyunTTS(nao_ip=host, nao_port=audio_port+2)
        
        # 创建音频socket
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_socket.bind((self.HOST, self.AUDIO_PORT))
        
        # 设置接收缓冲区大小
        self.audio_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        
        # 音频处理标志
        self.is_processing = True
        
        # 启动情绪检测线程
        self.emotion_thread = threading.Thread(target=self.process_emotion)
        self.emotion_thread.daemon = True
        self.emotion_thread.start()
    
    def process_emotion(self):
        """处理情绪检测结果"""
        while self.is_processing:
            try:
                # 从情绪检测器获取当前情绪
                emotion = self.emotion_detector.current_emotion
                if emotion:
                    # 更新Qwen模型的情绪状态
                    self.qwen_model.update_emotion(emotion)
                time.sleep(0.1)
            except Exception as e:
                print(f"处理情绪错误: {str(e)}")
                time.sleep(1)
    
    def start(self):
        """启动服务器"""
        print("服务器启动...")
        print(f"情绪检测端口: {self.emotion_detector.EMOTION_PORT}")
        print(f"音频端口: {self.AUDIO_PORT}")
        print(f"视频端口: {self.VIDEO_PORT}")
        print(f"TTS端口: {self.AUDIO_PORT+2}")
        
        # 启动音频处理线程
        audio_thread = threading.Thread(target=self.process_audio)
        audio_thread.daemon = True
        audio_thread.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n服务器停止")
            self.stop()
    
    def process_audio(self):
        """处理音频数据"""
        print("开始接收音频数据...")
        chunks = {}
        current_chunks = 0
        total_chunks = 0
        
        while self.is_processing:
            try:
                # 接收数据
                data, addr = self.audio_socket.recvfrom(65536)
                
                if len(data) == 4:  # 头部信息
                    total_chunks = struct.unpack('!I', data)[0]
                    chunks = {}
                    current_chunks = 0
                    continue
                    
                # 解析分片头部
                chunk_id = struct.unpack('!I', data[:4])[0]
                chunk_data = data[4:]
                
                # 存储分片
                chunks[chunk_id] = chunk_data
                current_chunks += 1
                
                # 检查是否接收完所有分片
                if current_chunks == total_chunks:
                    # 检查分片数量是否合理
                    if total_chunks <= 0:
                        print("警告：无效的分片数量")
                        chunks = {}
                        current_chunks = 0
                        total_chunks = 0
                        continue
                        
                    # 检查是否所有分片都已接收
                    missing_chunks = [i for i in range(total_chunks) if i not in chunks]
                    if missing_chunks:
                        print(f"警告：缺少分片 {missing_chunks}")
                        chunks = {}
                        current_chunks = 0
                        total_chunks = 0
                        continue
                    
                    # 重组音频数据
                    audio_data = b''.join([chunks[i] for i in range(total_chunks)])
                    
                    # 检查音频数据大小
                    if len(audio_data) == 0:
                        print("警告：重组后的音频数据为空")
                        chunks = {}
                        current_chunks = 0
                        total_chunks = 0
                        continue
                    
                    # 处理音频数据
                    processed_audio = process_audio_data(audio_data)
                    if processed_audio is None:
                        chunks = {}
                        current_chunks = 0
                        total_chunks = 0
                        continue
                    
                    # 创建结果队列
                    result_queue = Queue()
                    
                    # 创建并启动ASR和VAD线程
                    asr_thread = threading.Thread(target=asr_worker, args=(processed_audio, result_queue, self.asr_model))
                    vad_thread = threading.Thread(target=vad_worker, args=(processed_audio, result_queue, self.vad_model))
                    
                    asr_thread.start()
                    vad_thread.start()
                    
                    # 等待两个线程完成
                    asr_thread.join()
                    vad_thread.join()
                    
                    # 获取结果
                    asr_result = None
                    vad_result = False
                    while not result_queue.empty():
                        result_type, result = result_queue.get()
                        if result_type == 'asr':
                            asr_result = result
                        elif result_type == 'vad':
                            vad_result = result
                    
                    print(f"识别结果: {asr_result}")
                    
                    # 检测识别结果是否有效（同时考虑VAD结果）
                    if is_valid_text(asr_result, vad_result):
                        print("检测到有效语音，判断是指令还是对话...")
                        
                        # 获取当前情绪
                        current_emotion = self.emotion_detector.current_emotion
                        tts_emotion = None
                        
                        # 映射情绪到TTS情感类型
                        if current_emotion == "happy":
                            tts_emotion = "cheerful"
                        elif current_emotion == "sad":
                            tts_emotion = "sad" 
                        elif current_emotion == "angry":
                            tts_emotion = "angry"
                        
                        # 使用新的CommandHandler类处理命令
                        response = self.command_handler.process_command(asr_result)
                        print(f"处理结果: {response}")
 
                        # 只有当响应不为空字符串时才发送给NAO
                    chunks = {}
                    current_chunks = 0
                    total_chunks = 0
                    
            except Exception as e:
                print("处理音频错误: " + str(e))
                time.sleep(0.1)
    
    def stop(self):
        """停止服务器"""
        self.is_processing = False
        self.audio_socket.close()
        self.emotion_detector.stop()

def main():
    # 创建并启动服务器
    server = Server(host='0.0.0.0', audio_port=5002, video_port=5003)
    print("服务器配置：")
    print(f"  - 音频端口: {server.AUDIO_PORT}")
    print(f"  - 视频端口: {server.VIDEO_PORT}")
    print(f"  - 情绪检测端口: {server.emotion_detector.EMOTION_PORT}")
    print(f"  - TTS发送端口: 9561")
    server.start()

if __name__ == "__main__":
    main()