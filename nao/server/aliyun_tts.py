#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import json
import socket
import threading
import uuid
import wave
import base64
import hashlib
import hmac
import urllib
import datetime
import requests
import struct
from config import NAO_IP, NAO_PORT

class AliyunTTS:
    def __init__(self, nao_ip=NAO_IP, nao_port=9561):
        """
        初始化阿里云TTS客户端
        nao_ip: NAO机器人的IP地址
        nao_port: NAO上接收TTS音频的端口(固定为9561，与NAO客户端保持一致)
        """
        # NAO配置
        self.nao_ip = nao_ip
        self.nao_port = nao_port  # 使用固定端口9561发送TTS音频，与客户端一致
        # 调试输出实际使用的IP和端口
        print(f"阿里云TTS初始化: 目标NAO IP={nao_ip}, 端口={nao_port}")
        
        # 阿里云配置
        self.app_key = "zgPlHarA36L7wB0v"  # 应用密钥
        self.region = 'cn-shanghai'
        
        # TTS API配置
        self.tts_url = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/tts"
        
        # TTS参数
        self.format = 'wav'
        self.sample_rate = 16000
        # 可选的中文发音人：xiaoyun（女）、xiaogang（男）、xiaowei（女）、
        # ruoxi（女）、siqi（女）、sijia（女）、sicheng（男）、ninger（女）、
        # yina（女）
        self.voice = 'siqi'  # 使用思琪女声，发音更自然
        self.volume = 50
        self.speech_rate = 0  # 正常语速
        self.pitch_rate = 0   # 正常音调
        
        # 创建输出目录
        self.output_dir = 'tts_output'
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # 初始化Socket
        self.nao_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 设置发送缓冲区大小
        self.nao_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        
        print("阿里云TTS客户端初始化成功（使用硬编码令牌）")
    
    def get_token(self):
        """直接返回硬编码的Token"""
        # 硬编码的Token值，请将此替换为您已经获取到的有效Token
        hardcoded_token = "6f4122c97247496da047270933123e26"
        
        print(f"使用硬编码Token: {hardcoded_token[:10]}...")
        return hardcoded_token
    
    def _percent_encode(self, string):
        """URL编码，注意AWS和阿里云的编码规则有所不同"""
        res = urllib.parse.quote(string, safe='')
        res = res.replace('+', '%20')
        res = res.replace('*', '%2A')
        res = res.replace('%7E', '~')
        return res
    
    def send_audio_to_nao(self, audio_data):
        """发送音频数据到NAO"""
        try:
            # 分片发送数据 - 增大分片大小提高传输效率
            max_chunk_size = 4096  # 增大分片大小，从1024增加到4096
            
            # 将分片信息添加到头部
            total_chunks = (len(audio_data) + max_chunk_size - 1) // max_chunk_size
            
            # 减少冗余输出
            # print(f"准备发送音频到NAO: IP={self.nao_ip}, 端口={self.nao_port}, 总分片数={total_chunks}, 数据大小={len(audio_data)}字节")
            
            # 发送分片数量信息
            self.nao_socket.sendto(struct.pack('!I', total_chunks), (self.nao_ip, self.nao_port))
            # 将等待时间减少，提高响应速度
            time.sleep(0.005)  # 从0.01减少到0.005
            
            # 分片发送 - 批量发送以减少循环开销
            batch_size = 5  # 每次发送5个分片
            for i in range(0, total_chunks, batch_size):
                batch_end = min(i + batch_size, total_chunks)
                
                # 发送一批分片
                for j in range(i, batch_end):
                    start = j * max_chunk_size
                    end = min(start + max_chunk_size, len(audio_data))
                    chunk = audio_data[start:end]
                    
                    # 添加分片ID
                    chunk_with_header = struct.pack('!I', j) + chunk
                    
                    # 发送数据
                    self.nao_socket.sendto(chunk_with_header, (self.nao_ip, self.nao_port))
                
                # 批次之间短暂延迟，而不是每个分片都延迟
                if batch_end < total_chunks:
                    time.sleep(0.0005)  # 减少延迟时间，从0.001减少到0.0005
            
            # 减少冗余输出
            # print(f"音频数据发送完成: 总共 {total_chunks} 个分片")
                
        except Exception as e:
            print(f"发送音频到NAO失败: {e}")
    
    def synthesize_http(self, text):
        """使用HTTP接口合成语音(使用硬编码token)"""
        if not text:
            print("合成文本为空")
            return False
        
        try:
            # 创建输出文件
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.output_dir, f"tts_{timestamp}.wav")
            
            # 获取硬编码的token
            token = self.get_token()
            
            # 使用阿里云NLS实时语音合成HTTP接口
            url = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/tts"
            
            # 构建请求头
            headers = {
                "Content-Type": "application/json",
                "X-NLS-Token": token  # 在header中传递token
            }
            
            # 构建请求参数
            payload = {
                "appkey": self.app_key,
                "token": token,       # 在参数中也传递token
                "format": self.format,
                "sample_rate": self.sample_rate,
                "voice": self.voice,
                "volume": self.volume,
                "speech_rate": self.speech_rate,
                "pitch_rate": self.pitch_rate,
                "text": text
            }
            
            # 发送请求
            print(f"开始语音合成: {text}")
            response = requests.post(url, json=payload, headers=headers)
            
            # 检查响应
            if response.status_code != 200:
                print(f"合成失败，状态码: {response.status_code}, 响应: {response.text}")
                return False
            
            # 处理响应 - 保存为WAV文件
            with open(output_file, 'wb') as f:
                f.write(response.content)
            
            # 分片发送到NAO
            self.send_audio_to_nao(response.content)
            
            print(f"语音合成完成，已保存到: {output_file}")
            return True
            
        except Exception as e:
            print(f"语音合成错误: {e}")
            return False
    
    def synthesize_ws(self, text, emotion=None):
        """
        使用WebSocket进行实时语音合成（支持情感合成）
        参数:
            text: 要合成的文本
            emotion: 情感类型，可选值：cheerful(开心), sad(悲伤), angry(生气)
                    不指定则使用默认(中性)语调
        """
        if not text:
            print("合成文本为空")
            return False
            
        try:
            # 获取硬编码的token
            token = self.get_token()
                
            # 添加必要的导入
            try:
                import websocket
                import ssl
                import threading
            except ImportError:
                print("缺少websocket库，尝试使用pip安装")
                import subprocess
                subprocess.call(["pip", "install", "websocket-client"])
                import websocket
                import ssl
                import threading
                
            # 创建WAV文件用于保存音频
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.output_dir, f"tts_ws_{timestamp}.wav")
            
            # 创建音频数据缓冲区
            audio_buffer = bytearray()
            
            # 创建WSS URL
            url = f"wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?appkey={self.app_key}&token={token}&format=wav&sample_rate={self.sample_rate}"
            
            # 定义WebSocket回调
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    if "payload" in data:
                        audio_chunk = base64.b64decode(data["payload"])
                        audio_buffer.extend(audio_chunk)
                except Exception as e:
                    print(f"处理WebSocket消息错误: {e}")
            
            def on_error(ws, error):
                print(f"WebSocket错误: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                print("WebSocket连接关闭")
                
                # 保存音频文件
                if audio_buffer:
                    with open(output_file, 'wb') as f:
                        f.write(audio_buffer)
                    print(f"语音合成完成，已保存到: {output_file}")
                    
                    # 发送到NAO
                    self.send_audio_to_nao(audio_buffer)
            
            def on_open(ws):
                def run():
                    try:
                        # 构建合成请求
                        payload = {
                            "header": {
                                "appkey": self.app_key,
                                "message_id": str(int(time.time() * 1000)),
                                "namespace": "SpeechSynthesizer",
                                "name": "StartSynthesis"
                            },
                            "payload": {
                                "text": text,
                                "format": "wav",
                                "sample_rate": self.sample_rate,
                                "voice": self.voice,
                                "volume": self.volume,
                                "speech_rate": self.speech_rate,
                                "pitch_rate": self.pitch_rate,
                                "enable_subtitle": False
                            }
                        }
                        
                        # 如果指定了情感，添加到请求中
                        if emotion and emotion in ["cheerful", "sad", "angry"]:
                            payload["payload"]["emotion"] = emotion
                            
                        # 发送请求
                        ws.send(json.dumps(payload))
                    except Exception as e:
                        print(f"发送WebSocket请求错误: {e}")
                
                threading.Thread(target=run).start()
            
            # 创建WebSocket连接
            print(f"开始WebSocket语音合成: {text}")
            ws = websocket.WebSocketApp(url,
                                      on_open=on_open,
                                      on_message=on_message,
                                      on_error=on_error,
                                      on_close=on_close)
            
            # 建立连接并等待完成
            ws_thread = threading.Thread(target=ws.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}})
            ws_thread.start()
            
            # 等待合成完成(最多30秒)
            timeout = 30
            ws_thread.join(timeout)
            
            if ws_thread.is_alive():
                print("WebSocket合成超时，强制关闭")
                ws.close()
                return False
                
            return True
            
        except Exception as e:
            print(f"WebSocket语音合成错误: {e}")
            return False

    def process_text(self, text, use_ws=True, emotion=None):
        """
        处理文本，按标点符号分段合成
        参数:
            text: 要合成的文本
            use_ws: 是否优先使用WebSocket方式
            emotion: 情感类型(仅WebSocket方式支持)
        """
        if not text:
            return False
            
        # 简化分段处理 - 只在较长文本时才进行分段
        if len(text) > 100:
            # 按标点符号分段
            import re
            segments = re.split(r'([。！？.!?])', text)
            
            # 重组分段（保留标点符号）
            i = 0
            while i < len(segments) - 1:
                if i + 1 < len(segments):
                    segments[i] = segments[i] + segments[i+1]
                    segments.pop(i+1)
                i += 1
            
            # 只保留有内容的分段
            segments = [s for s in segments if s.strip()]
            
            # 并行合成 - 可选，但需要确保NAO能处理多个音频片段
            # 这里仍使用串行处理，但减少等待时间
            for segment in segments:
                self.synthesize(segment, use_ws, emotion)
                # 将等待时间减少，从0.1减少到0.05
                time.sleep(0.05)
        else:
            # 短文本直接合成，不分段，减少处理开销
            self.synthesize(text, use_ws, emotion)
                
        return True
        
    def synthesize(self, text, use_ws=True, emotion=None):
        """
        合成文本为语音(自动选择最佳方式)
        参数:
            text: 要合成的文本
            use_ws: 是否优先使用WebSocket方式
            emotion: 情感类型(仅WebSocket方式支持)
        """
        # 优化合成方法选择 - 除非特别需要情感或长文本，否则使用更快的HTTP方式
        if use_ws and emotion:
            return self.synthesize_ws(text, emotion)
        else:
            # 对大多数情况使用HTTP方式，更快
            return self.synthesize_http(text)

def test_aliyun_tts():
    """测试阿里云TTS功能"""
    tts = AliyunTTS()
    
    # 测试普通合成
    print("\n--- 测试普通文本合成 ---")
    test_text = "你好，我是一个测试语音。今天天气真不错！你觉得呢？"
    tts.process_text(test_text)
    
    # 测试情感合成
    emotions = ["cheerful", "sad", "angry"]
    emotion_texts = {
        "cheerful": "太好了！我们赢得了比赛，我真的非常开心！",
        "sad": "这个消息让我很难过，我感到非常沮丧。",
        "angry": "这太过分了！我非常生气和不满！"
    }
    
    for emotion in emotions:
        print(f"\n--- 测试{emotion}情感合成 ---")
        tts.process_text(emotion_texts[emotion], True, emotion)
        time.sleep(1)
        
    print("\n测试完成！")

if __name__ == '__main__':
    print("开始测试阿里云TTS...")
    test_aliyun_tts() 