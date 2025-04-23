# -*- coding: utf-8 -*-

import cv2
import numpy as np
import torch
from ultralytics import YOLO
import time
import os
import socket
import struct
import threading
from config import NAO_IP, NAO_PORT

class ObjectDetector:
    def __init__(self, model_path="server/model/yolov8n.pt", nao_ip=NAO_IP, nao_port=5003):
        """初始化物体检测器
        
        Args:
            model_path: YOLOv8模型路径，如果为None则使用预训练模型
            nao_ip: NAO机器人IP地址
            nao_port: NAO机器人视频端口，默认为5003（视频端口）
        """
        try:
            # 如果没有指定模型路径，使用预训练模型
            if model_path is None or not os.path.exists(model_path):
                print("使用YOLOv8预训练模型...")
                self.model = YOLO("yolov8n.pt")
            else:
                print(f"加载自定义模型: {model_path}")
                self.model = YOLO(model_path)
            
            # 设置检测参数
            self.conf_threshold = 0.5  # 置信度阈值
            self.iou_threshold = 0.45   # IOU阈值
            
            # 加载COCO类别名称
            self.class_names = self.model.names
            
            # NAO相关配置
            self.nao_ip = nao_ip
            self.nao_port = nao_port
            
            # 最近的检测结果
            self.last_detected_objects = []
            self.last_detection_time = 0
            
            # 标记是否正在从NAO获取视频
            self.is_receiving_from_nao = False
            self.nao_video_thread = None
            
            print("物体检测器初始化成功")
        except Exception as e:
            print(f"初始化物体检测器失败: {str(e)}")
            raise
    
    def detect(self, image):
        """检测图像中的物体
        
        Args:
            image: 输入图像，可以是numpy数组或图像路径
            
        Returns:
            detected_objects: 检测到的物体列表，每个元素为(类别名称, 置信度)
        """
        try:
            # 如果输入是图像路径，则读取图像
            if isinstance(image, str):
                image = cv2.imread(image)
                if image is None:
                    raise ValueError(f"无法读取图像: {image}")
            
            # 执行检测
            results = self.model(image, conf=self.conf_threshold, iou=self.iou_threshold)
            
            # 提取检测结果
            detected_objects = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # 获取类别ID和置信度
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    # 获取类别名称
                    cls_name = self.class_names[cls_id]
                    
                    # 添加到结果列表
                    detected_objects.append((cls_name, conf))
            
            # 更新最近的检测结果
            self.last_detected_objects = detected_objects
            self.last_detection_time = time.time()
            
            return detected_objects
        except Exception as e:
            print(f"物体检测失败: {str(e)}")
            return []
    
    def detect_from_camera(self, camera_id=0, timeout=5):
        """从本地摄像头检测物体
        
        Args:
            camera_id: 摄像头ID
            timeout: 超时时间（秒）
            
        Returns:
            detected_objects: 检测到的物体列表
        """
        try:
            # 打开摄像头
            cap = cv2.VideoCapture(camera_id)
            if not cap.isOpened():
                raise ValueError(f"无法打开摄像头: {camera_id}")
            
            # 设置超时
            start_time = time.time()
            
            # 读取几帧以确保摄像头稳定
            for _ in range(5):
                ret, _ = cap.read()
                if not ret:
                    raise ValueError("无法从摄像头读取图像")
            
            # 读取一帧进行检测
            ret, frame = cap.read()
            if not ret:
                raise ValueError("无法从摄像头读取图像")
            
            # 释放摄像头
            cap.release()
            
            # 执行检测
            detected_objects = self.detect(frame)
            
            return detected_objects
        except Exception as e:
            print(f"从摄像头检测物体失败: {str(e)}")
            return []
    
    def detect_from_nao(self):
        """从NAO机器人的摄像头检测物体
        
        Returns:
            detected_objects: 检测到的物体列表，如果没有最近的检测结果则返回空列表
        """
        # 检查是否有最近的检测结果
        if not self.is_receiving_from_nao:
            # 如果没有从NAO接收视频，启动接收线程
            self.start_nao_video_receiver()
            # 等待一会儿以获取视频帧
            time.sleep(1)
        
        # 检查是否有最近的检测结果
        if self.last_detected_objects and (time.time() - self.last_detection_time) < 3:
            # 如果有最近的检测结果且不超过3秒，直接返回
            return self.last_detected_objects
        else:
            # 如果没有最近的检测结果或结果过期，返回空列表
            return []
    
    def start_nao_video_receiver(self):
        """启动从NAO接收视频的线程"""
        if not self.is_receiving_from_nao:
            # 创建并启动接收线程
            self.is_receiving_from_nao = True
            self.nao_video_thread = threading.Thread(target=self._receive_nao_video)
            self.nao_video_thread.daemon = True
            self.nao_video_thread.start()
            print("开始从NAO接收视频...")
    
    def stop_nao_video_receiver(self):
        """停止从NAO接收视频"""
        self.is_receiving_from_nao = False
        if self.nao_video_thread:
            self.nao_video_thread.join(timeout=1)
            print("停止从NAO接收视频")
    
    def _receive_nao_video(self):
        """接收NAO视频数据并处理"""
        try:
            # 创建UDP socket用于接收视频
            video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            video_socket.bind(("0.0.0.0", self.nao_port))
            
            # 设置接收缓冲区大小
            video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            
            chunks = {}
            current_chunks = 0
            total_chunks = 0
            
            while self.is_receiving_from_nao:
                try:
                    # 接收数据
                    data, addr = video_socket.recvfrom(65536)
                    
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
                        # 重组图像数据
                        image_data = b''.join([chunks[i] for i in range(total_chunks)])
                        
                        # 解码图像
                        image = cv2.imdecode(np.frombuffer(image_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                        
                        if image is not None:
                            # 检测物体
                            self.detect(image)
                        
                        # 重置
                        chunks = {}
                        current_chunks = 0
                        total_chunks = 0
                        
                except Exception as e:
                    print(f"处理NAO视频帧错误: {str(e)}")
                    time.sleep(0.1)
            
            # 关闭socket
            video_socket.close()
        except Exception as e:
            print(f"接收NAO视频错误: {str(e)}")
            self.is_receiving_from_nao = False
    
    def format_detection_result(self, detected_objects):
        """格式化检测结果为自然语言描述
        
        Args:
            detected_objects: 检测到的物体列表
            
        Returns:
            description: 自然语言描述
        """
        if not detected_objects:
            return "我没有看到任何物体"
        
        # 统计每个类别的数量
        object_counts = {}
        for obj_name, _ in detected_objects:
            if obj_name in object_counts:
                object_counts[obj_name] += 1
            else:
                object_counts[obj_name] = 1
        
        # 构建描述
        if len(object_counts) == 1:
            obj_name = list(object_counts.keys())[0]
            count = object_counts[obj_name]
            if count == 1:
                return f"我看到了一个{obj_name}"
            else:
                return f"我看到了{count}个{obj_name}"
        else:
            description = "我看到了"
            items = []
            for obj_name, count in object_counts.items():
                if count == 1:
                    items.append(f"一个{obj_name}")
                else:
                    items.append(f"{count}个{obj_name}")
            
            if len(items) == 2:
                description += f"{items[0]}和{items[1]}"
            else:
                description += "、".join(items[:-1]) + f"和{items[-1]}"
            
            return description

if __name__ == "__main__":
    # 测试代码
    try:
        detector = ObjectDetector()
        print("开始测试物体检测...")
        
        # 测试从摄像头检测
        print("从摄像头检测物体...")
        detected_objects = detector.detect_from_camera()
        
        # 打印检测结果
        print("检测到的物体:")
        for obj_name, conf in detected_objects:
            print(f"- {obj_name}: {conf:.2f}")
        
        # 打印自然语言描述
        description = detector.format_detection_result(detected_objects)
        print(f"描述: {description}")
        
        print("测试完成")
    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}") 