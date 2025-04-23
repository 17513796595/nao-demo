# -*- coding: utf-8 -*-
import time
import naoqi
from naoqi import ALProxy
import socket
import struct
import cv2
import numpy as np
import threading

import config

class VideoRecorder:
    def __init__(self, nao_ip=config.NAO_IP, nao_port=config.NAO_PORT, server_ip=config.SERVER_IP, server_port=config.SERVER_PORT, emotion_port=5005):
        # 初始化视频代理
        self.video_device = ALProxy("ALVideoDevice", nao_ip, nao_port)
        self.camera_name = "camera"
        self.resolution = 2  # VGA
        self.color_space = 11  # BGR
        self.fps = 15
        
        # 订阅摄像头
        self.camera_id = self.video_device.subscribeCamera(
            self.camera_name, 0, self.resolution, self.color_space, self.fps
        )
        
        # 服务器配置
        self.SERVER_IP = server_ip
        self.SERVER_PORT = server_port  # 对象检测端口 (默认5003)
        self.EMOTION_PORT = emotion_port  # 情绪检测端口 (默认5004)
        
        # 创建UDP socket用于发送视频到对象检测服务
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        
        # 创建UDP socket用于发送视频到情绪检测服务
        self.emotion_video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.emotion_video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        
        # 创建UDP socket用于接收情绪类型
        self.emotion_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.emotion_socket.bind(("0.0.0.0", server_port + 1))  # 使用不同的端口接收情绪
        
        # 额外的视频目标
        self.extra_video_destinations = {}
        
        # 启动接收情绪的线程
        self.emotion_thread = threading.Thread(target=self.receive_emotion)
        self.emotion_thread.daemon = True
        self.emotion_thread.start()
        
        # 视频传输标志
        self.is_streaming = False
        
    def start_streaming(self):
        """开始视频流传输"""
        self.is_streaming = True
        print("视频流传输开始，将发送视频到对象检测端口 %s 和情绪检测端口 %s" % (self.SERVER_PORT, self.EMOTION_PORT))
        frame_count = 0
        last_log_time = time.time()
        
        while self.is_streaming:
            try:
                # 获取图像数据
                image_data = self.video_device.getImageRemote(self.camera_id)
                if image_data:
                    # 将图像数据转换为numpy数组
                    width = image_data[0]
                    height = image_data[1]
                    array = image_data[6]
                    
                    # 将图像数据转换为numpy数组
                    image = np.frombuffer(array, dtype=np.uint8)
                    image = image.reshape((height, width, 3))
                    
                    # 压缩图像
                    _, img_encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    
                    # 将numpy数组转换为bytes
                    img_bytes = img_encoded.tobytes()
                    
                    # 分片发送到对象检测服务
                    self.send_video_data(img_bytes, self.video_socket, self.SERVER_IP, self.SERVER_PORT)
                    
                    # 分片发送到情绪检测服务
                    self.send_video_data(img_bytes, self.emotion_video_socket, self.SERVER_IP, self.EMOTION_PORT)
                    
                    # 计数并周期性打印
                    frame_count += 1
                    current_time = time.time()
                    if current_time - last_log_time >= 30.0:  # 每30秒打印一次
                        print("视频流状态：已发送 %d 帧，目标：对象检测 %s，情绪检测 %s" % (frame_count, self.SERVER_PORT, self.EMOTION_PORT))
                        last_log_time = current_time
                    
                    # 发送到额外的视频目标
                    for dest_key, (socket_obj, target_ip, target_port) in self.extra_video_destinations.items():
                        self.send_video_data(img_bytes, socket_obj, target_ip, target_port)
                
                time.sleep(1.0/self.fps)
                
            except Exception as e:
                print("视频传输错误: " + str(e))
                time.sleep(1)
    
    def add_extra_video_destination(self, dest_key, target_ip, target_port):
        """添加额外的视频目标"""
        if dest_key not in self.extra_video_destinations:
            # 创建新的UDP socket
            new_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            new_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self.extra_video_destinations[dest_key] = (new_socket, target_ip, target_port)
            print("已添加新的视频目标: " + dest_key + " -> " + target_ip + ":" + str(target_port))
            return True
        else:
            print("视频目标已存在: " + dest_key)
            return False
    
    def remove_extra_video_destination(self, dest_key):
        """移除额外的视频目标"""
        if dest_key in self.extra_video_destinations:
            socket_obj, _, _ = self.extra_video_destinations[dest_key]
            socket_obj.close()
            del self.extra_video_destinations[dest_key]
            print("已移除视频目标: " + dest_key)
            return True
        else:
            print("视频目标不存在: " + dest_key)
            return False
    
    def send_video_data(self, img_bytes, socket_obj, target_ip, target_port):
        """发送视频数据到指定目标"""
        chunk_size = 1400
        total_chunks = (len(img_bytes) + chunk_size - 1) // chunk_size
        
        # 发送头部信息
        header = struct.pack('!I', total_chunks)
        socket_obj.sendto(header, (target_ip, target_port))
        
        # 分片发送数据
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(img_bytes))
            chunk = img_bytes[start:end]
            
            chunk_header = struct.pack('!I', i)
            chunk_with_header = chunk_header + chunk
            
            socket_obj.sendto(chunk_with_header, (target_ip, target_port))
            time.sleep(0.001)
    
    def receive_emotion(self):
        """接收服务端返回的情绪类型"""
        print("等待接收情绪类型...")
        while True:
            try:
                data, addr = self.emotion_socket.recvfrom(1024)
                if data:
                    try:
                        # 在Python 2.7中正确处理中文字符
                        emotion = data.decode('utf-8').encode('utf-8')
                        print("收到情绪类型: " + emotion)
                    except UnicodeDecodeError:
                        print("收到无效的情绪数据")
                    except UnicodeEncodeError:
                        print("情绪数据编码错误")
                    # 在这里可以根据情绪类型进行相应的处理
            except Exception as e:
                print("接收情绪错误: " + str(e))
                time.sleep(1)
    
    def stop_streaming(self):
        """停止视频流传输"""
        self.is_streaming = False
        self.video_device.unsubscribe(self.camera_id)
        self.video_socket.close()
        self.emotion_video_socket.close()
        
        # 关闭额外的视频目标
        for dest_key in list(self.extra_video_destinations.keys()):
            self.remove_extra_video_destination(dest_key)
            
        self.emotion_socket.close()