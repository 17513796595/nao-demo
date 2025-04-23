#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import time
import threading
import struct
import os
import wave
from naoqi import ALProxy
import config

class AliyunAudioPlayer:
    """
    用于NAO客户端接收和播放阿里云TTS合成的音频
    """
    def __init__(self, nao_ip=config.NAO_IP, nao_port=config.NAO_PORT+2):
        """初始化音频播放器"""
        # NAO配置
        self.nao_ip = nao_ip
        self.nao_port = nao_port  # 使用新的端口，避免和现有功能冲突
        
        # 打印实际使用的NAO IP和端口
        print("阿里云音频播放器初始化: NAO IP=%s, 端口=%s" % (nao_ip, nao_port))
        
        # 初始化播放器
        try:
            self.audio_player = ALProxy("ALAudioPlayer", nao_ip, config.NAO_PORT)
            print("音频播放器初始化成功")
        except Exception as e:
            print("音频播放器初始化失败: " + str(e))
            return
        
        # 创建临时目录
        self.temp_dir = "/home/nao/naoqi/aliyun_audio"
        try:
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
        except Exception as e:
            print("创建临时目录失败: " + str(e))
            self.temp_dir = "/home/nao/naoqi"
        
        # 创建UDP socket用于接收音频
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_socket.bind(("0.0.0.0", self.nao_port))
        
        # 设置接收缓冲区大小
        self.audio_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        
        # 播放状态标志和锁
        self._is_playing = False
        self._playing_lock = threading.Lock()
        
        # 当前音频数据
        self.current_audio_data = bytearray()
        self.current_file_index = 0
        
        # 启动接收线程
        self.is_receiving = True
        self.receiver_thread = threading.Thread(target=self.receive_audio)
        self.receiver_thread.daemon = True
        self.receiver_thread.start()
        
        print("阿里云音频播放器已启动，监听端口: %d" % self.nao_port)
    
    @property
    def is_playing(self):
        """获取播放状态"""
        with self._playing_lock:
            return self._is_playing
    
    @is_playing.setter
    def is_playing(self, value):
        """设置播放状态"""
        with self._playing_lock:
            old_value = self._is_playing
            self._is_playing = value
            # 如果状态发生变化，则打印日志
            if old_value != value:
                print("阿里云TTS播放状态变更: %s -> %s" % (old_value, value))
                
                # 如果播放结束，发送信号
                if old_value and not value:
                    # 此处可以添加播放结束的回调或信号通知
                    pass
    
    def receive_audio(self):
        """接收音频数据线程"""
        print("阿里云音频接收线程启动，监听端口: %d, 等待数据..." % self.nao_port)
        
        # 分片重组相关变量
        chunks = {}
        total_chunks = 0
        current_chunks = 0
        last_chunk_time = time.time()
        
        while self.is_receiving:
            try:
                # 接收数据
                data, addr = self.audio_socket.recvfrom(65536)
                # 减少日志输出以提高性能
                # print("收到数据包，长度: %d, 来源: %s" % (len(data), addr))
                
                # 检查是否是控制命令
                if len(data) < 10 and data.startswith(b"CMD:"):
                    cmd = data[4:].decode('utf-8')
                    if cmd == "STOP":
                        print("收到停止命令")
                        self.stop_playing()
                    continue
                
                # 检查是否是分片数量信息
                if len(data) == 4:
                    # 这是分片数量信息
                    total_chunks = struct.unpack('!I', data)[0]
                    # print("收到分片信息，总分片数: %d" % total_chunks)
                    chunks = {}
                    current_chunks = 0
                    last_chunk_time = time.time()
                    continue
                
                # 检查是否是分片数据
                if len(data) > 4:
                    try:
                        # 解析分片ID
                        chunk_id = struct.unpack('!I', data[:4])[0]
                        chunk_data = data[4:]
                        # print("收到分片 #%d, 数据长度: %d" % (chunk_id, len(chunk_data)))
                        
                        # 存储分片
                        chunks[chunk_id] = chunk_data
                        current_chunks += 1
                        last_chunk_time = time.time()
                        
                        # 如果收到所有分片或者超过一定时间未收到新分片，则处理当前已收到的分片
                        # 这可以提高响应速度，即使部分分片丢失也能播放
                        if current_chunks == total_chunks or (current_chunks > 0 and time.time() - last_chunk_time > 0.5):
                            # 按顺序重组所有分片
                            self.current_audio_data = bytearray()
                            for i in range(total_chunks):
                                if i in chunks:
                                    self.current_audio_data.extend(chunks[i])
                                else:
                                    # 处理丢失的分片 - 可以添加静音数据或直接跳过
                                    pass
                            
                            # 保存并播放
                            if len(self.current_audio_data) > 0:
                                # print("准备保存和播放音频，数据长度: %d" % len(self.current_audio_data))
                                
                                # 直接启动新线程进行保存和播放，而不阻塞接收线程
                                playback_thread = threading.Thread(target=self.save_and_play_audio)
                                playback_thread.daemon = True
                                playback_thread.start()
                            
                            # 重置状态
                            chunks = {}
                            total_chunks = 0
                            current_chunks = 0
                    except Exception as e:
                        print("处理分片数据错误: " + str(e))
                else:
                    # 旧格式，直接添加数据
                    # print("收到未分片的音频数据，长度: %d" % len(data))
                    self.current_audio_data.extend(data)
                    
                    # 当达到一定大小后保存并播放
                    if len(self.current_audio_data) > 16000:  # 减小阈值，提高响应速度
                        # print("未分片数据达到阈值，准备保存和播放")
                        
                        # 直接启动新线程进行保存和播放，而不阻塞接收线程
                        playback_thread = threading.Thread(target=self.save_and_play_audio)
                        playback_thread.daemon = True
                        playback_thread.start()
            
            except Exception as e:
                print("接收音频错误: " + str(e))
                time.sleep(0.1)
    
    def save_and_play_audio(self):
        """保存并播放当前音频数据"""
        try:
            # 获取当前音频数据的副本，避免并发修改
            current_data = self.current_audio_data
            # 清空原始缓冲区，允许接收新数据
            self.current_audio_data = bytearray()
            
            # 如果数据太少，不处理
            if len(current_data) < 1000:
                return
                
            # 生成文件名
            filename = os.path.join(self.temp_dir, "audio_%d.wav" % self.current_file_index)
            self.current_file_index = (self.current_file_index + 1) % 10  # 循环使用10个文件
            
            # 保存为WAV文件 - 不使用with语句，而是显式打开和关闭
            wf = wave.open(filename, 'wb')
            try:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(current_data)
            finally:
                wf.close()
            
            # 播放音频
            if not self.is_playing:
                self.is_playing = True
                try:
                    # 使用NAO的音频播放器播放 - 设置更高的音量和优先级
                    volume = 1.0  # 最大音量
                    self.audio_player.playFile(filename, volume, 0)  # 前景层播放，避免被打断
                    self.is_playing = False
                except Exception as e:
                    print("播放音频失败: " + str(e))
                    self.is_playing = False
            
        except Exception as e:
            print("保存和播放音频失败: " + str(e))
            self.current_audio_data = bytearray()
    
    def stop_playing(self):
        """停止当前播放"""
        try:
            self.audio_player.stopAll()
            self.is_playing = False
            self.current_audio_data = bytearray()
        except Exception as e:
            print("停止播放失败: " + str(e))
    
    def shutdown(self):
        """关闭播放器"""
        self.is_receiving = False
        self.stop_playing()
        if hasattr(self, 'audio_socket'):
            self.audio_socket.close()
        print("阿里云音频播放器已关闭")

def main():
    """主函数，用于测试功能"""
    player = AliyunAudioPlayer()
    
    try:
        print("阿里云音频播放器已启动，按Ctrl+C退出...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已退出")
        player.shutdown()

if __name__ == "__main__":
    main() 