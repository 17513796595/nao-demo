# -*- coding: utf-8 -*-
import os
os.environ['YOLO_VERBOSE'] = 'False'

import cv2
import numpy as np
from ultralytics import YOLO
import socket
import struct
import threading
import time
from config import NAO_IP, NAO_PORT

# 禁用YOLO的输出
import ultralytics
#ultralytics.yolo.utils.logging.set_console_level(50)  # 设置日志级别为CRITICAL

class EmotionDetector:
    def __init__(self, face_model_path="server/model/yolov8n-face.pt", emotion_model_path="server/model/best.pt", nao_ip=NAO_IP, nao_port=NAO_PORT, emotion_port=5004):
        # 初始化模型状态标志
        self.model_loaded = False
        
        try:
            print(f"加载人脸检测模型: {face_model_path}")
            # 加载人脸检测模型
            self.face_detector = YOLO(face_model_path)
            print(f"加载情绪识别模型: {emotion_model_path}")
            # 加载情绪识别模型
            self.emotion_model = YOLO(emotion_model_path)
            
            # 尝试禁用YOLO的打印信息
            try:
                if hasattr(self.face_detector, 'predictor') and hasattr(self.face_detector.predictor, 'args'):
                    self.face_detector.predictor.args.verbose = False
                if hasattr(self.emotion_model, 'predictor') and hasattr(self.emotion_model.predictor, 'args'):
                    self.emotion_model.predictor.args.verbose = False
            except Exception as e:
                print(f"设置模型参数时出错: {e}")
                
            # 标记模型已成功加载
            self.model_loaded = True
            print("情绪检测模型加载成功")
        except Exception as e:
            print(f"模型加载失败: {e}")
            print("将使用默认情绪(neutral)")
        
        # 服务器配置
        self.SERVER_IP = nao_ip
        self.SERVER_PORT = nao_port
        self.EMOTION_PORT = emotion_port  # 初始端口
        
        # 创建UDP socket用于接收视频
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # 尝试绑定socket到指定端口，如果失败则尝试其他端口
        max_attempts = 5
        current_port = self.EMOTION_PORT
        
        for attempt in range(max_attempts):
            try:
                print(f"尝试绑定情绪检测socket到端口 {current_port}...")
                self.video_socket.bind(("0.0.0.0", current_port))
                self.EMOTION_PORT = current_port  # 更新实际使用的端口
                print(f"成功绑定情绪检测socket到端口 {self.EMOTION_PORT}")
                break
            except socket.error as e:
                print(f"无法绑定情绪检测到端口 {current_port}: {e}")
                current_port += 1
                if attempt == max_attempts - 1:
                    raise Exception(f"无法找到可用端口，已尝试端口 {self.EMOTION_PORT} 到 {current_port-1}")
        
        # 创建UDP socket用于发送情绪
        self.emotion_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # 设置接收缓冲区大小
        self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        
        # 情绪类别
        self.emotions = [
            "angry",    # 生气
            "disgust",  # 厌恶
            "fear",     # 恐惧
            "happy",    # 开心
            "sad",      # 悲伤
            "surprise", # 惊讶
            "neutral"   # 平静
        ]
        
        # 当前检测到的情绪
        self.current_emotion = "neutral"
        
        # 上一次发送的情绪
        self.last_sent_emotion = None
        
        # 上一次发送情绪的时间
        self.last_emotion_sent_time = 0
        
        # 上一次打印情绪的时间
        self.last_emotion_print_time = 0
        
        # 情绪发送的最小间隔时间（秒）
        self.emotion_send_interval = 2.0
        
        # 情绪打印的最小间隔时间（秒）
        self.emotion_print_interval = 30.0
        
        # 视频处理标志
        self.is_processing = True
        
        print(f"情绪检测初始化完成，监听端口: {self.EMOTION_PORT}")
        # 启动接收视频的线程
        self.receive_thread = threading.Thread(target=self.receive_video)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
    def receive_video(self):
        """接收视频数据并处理"""
        print("开始接收视频数据（情绪检测模块）...")
        print(f"监听端口: {self.EMOTION_PORT}, 等待视频数据...")
        chunks = {}
        current_chunks = 0
        total_chunks = 0
        last_log_time = time.time()
        video_frames_received = 0
        
        while self.is_processing:
            try:
                # 接收数据
                data, addr = self.video_socket.recvfrom(65536)
                
                # 周期性地打印接收状态
                current_time = time.time()
                if current_time - last_log_time >= 30.0:  # 每30秒打印一次状态
                    print(f"情绪检测模块状态：已接收 {video_frames_received} 帧视频")
                    last_log_time = current_time
                
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
                    video_frames_received += 1
                    if video_frames_received == 1 or video_frames_received % 50 == 0:
                        print(f"情绪检测模块已接收 {video_frames_received} 帧视频")
                    
                    # 重组图像数据
                    image_data = b''.join([chunks[i] for i in range(total_chunks)])
                    
                    # 解码图像
                    image = cv2.imdecode(np.frombuffer(image_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if image is not None:
                        # 检测情绪
                        emotion = self.detect_emotion(image)
                        
                        # 更新当前情绪
                        if emotion:
                            # 只有在情绪变化或经过较长时间间隔后才打印情绪信息
                            current_time = time.time()
                            if (emotion != self.current_emotion or 
                                current_time - self.last_emotion_print_time >= self.emotion_print_interval):
                                print(f"检测到情绪: {emotion}")
                                self.last_emotion_print_time = current_time
                            
                            # 更新当前情绪状态
                            self.current_emotion = emotion
                        
                        # 只有当情绪变化或足够长时间未发送时才发送情绪
                        current_time = time.time()
                        if (self.current_emotion != self.last_sent_emotion or 
                            current_time - self.last_emotion_sent_time >= self.emotion_send_interval):
                            
                            # 从客户端地址获取IP
                            client_ip = addr[0]
                            # 发送情绪类型到视频发送方的情绪接收端口（基于视频端口+1）
                            try:
                                # 计算接收情绪的端口（NAO端视频端口+1）
                                emotion_port = self.SERVER_PORT + 1
                                self.emotion_socket.sendto(self.current_emotion.encode('utf-8'), (client_ip, emotion_port))
                                print(f"已发送情绪 '{self.current_emotion}' 到 {client_ip}:{emotion_port}")
                                
                                # 更新上次发送的情绪和时间
                                self.last_sent_emotion = self.current_emotion
                                self.last_emotion_sent_time = current_time
                            except Exception as e:
                                print(f"发送情绪失败: {str(e)}")
                    else:
                        print("警告：无法解码图像数据")
                    
                    # 重置
                    chunks = {}
                    current_chunks = 0
                    total_chunks = 0
                    
            except Exception as e:
                print(f"接收视频错误: {str(e)}")
                time.sleep(0.1)
    
    def detect_emotion(self, image):
        """检测图像中的情绪"""
        # 如果模型未成功加载，直接返回默认情绪
        if not getattr(self, 'model_loaded', False):
            return "neutral"
            
        try:
            # 第一阶段：检测人脸
            face_results = self.face_detector(image)[0]
            
            if len(face_results.boxes.data) == 0:
                # 周期性地打印未检测到人脸的信息（避免日志过多）
                current_time = time.time()
                if current_time - getattr(self, 'last_face_log_time', 0) > 10:  # 每10秒最多打印一次
                    print("未检测到人脸")
                    self.last_face_log_time = current_time
                return "neutral"
            
            best_emotion = None
            best_confidence = 0
            
            for result in face_results.boxes.data:
                x1, y1, x2, y2, score, class_id = result
                
                if score > 0.5:  # 置信度阈值
                    # 打印人脸检测置信度
                    print(f"检测到人脸，置信度: {score:.2f}")
                    
                    # 裁剪人脸区域
                    face = image[int(y1):int(y2), int(x1):int(x2)]
                    
                    # 确保裁剪的区域有效
                    if face.size == 0:
                        print("警告：裁剪的人脸区域无效")
                        continue
                    
                    # 第二阶段：进行情绪识别
                    emotion_result = self.emotion_model(face)[0]
                    if len(emotion_result.boxes.data) > 0:
                        emotion_class = int(emotion_result.boxes.cls[0])
                        emotion_conf = float(emotion_result.boxes.conf[0])
                        
                        # 打印情绪识别结果
                        print(f"情绪检测结果: {self.emotions[emotion_class]}, 置信度: {emotion_conf:.2f}")
                        
                        # 更新置信度最高的情绪
                        if emotion_conf > best_confidence:
                            best_confidence = emotion_conf
                            best_emotion = self.emotions[emotion_class]
            
            if best_emotion is None:
                print("无法识别情绪，使用默认情绪")
            else:
                print(f"最终情绪判断: {best_emotion}, 置信度: {best_confidence:.2f}")
            
            return best_emotion if best_emotion else "neutral"
            
        except Exception as e:
            print(f"情绪检测错误: {str(e)}")
            return "neutral"
    
    def stop(self):
        """停止处理"""
        self.is_processing = False
        self.video_socket.close()
        self.emotion_socket.close() 