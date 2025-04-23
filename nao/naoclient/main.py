# -*- coding: utf-8 -*-
import time
import naoqi
from naoqi import ALProxy
import threading
import Queue
import socket
import struct

import config
from audio import AudioRecorder
from video import VideoRecorder
from motion_controller import MotionController
from aliyun_audio_player import AliyunAudioPlayer
from network import NetworkManager, NetworkClient

def main():
    try:
        # 打印配置信息
        print("当前配置:")
        print("NAO IP: {}".format(config.NAO_IP))
        print("NAO PORT: {}".format(config.NAO_PORT))
        print("服务器 IP: {}".format(config.SERVER_IP))
        print("服务器音频端口: {}".format(config.SERVER_PORT))
        print("服务器视频端口: {}".format(config.SERVER_PORT + 1))
        print("服务器情绪检测端口: 5005")  # 固定端口5005
        print("阿里云TTS接收端口: 9561")  # 固定端口9561
        
        # 创建网络客户端
        network_client = NetworkClient()
        
        # 初始化音频录制器
        audio_recorder = AudioRecorder(
            nao_ip=config.NAO_IP,
            nao_port=config.NAO_PORT,
            server_ip=config.SERVER_IP,
            server_port=config.SERVER_PORT
        )
        
        # 初始化视频录制器
        video_recorder = VideoRecorder(
            nao_ip=config.NAO_IP,
            nao_port=config.NAO_PORT,
            server_ip=config.SERVER_IP,
            server_port=config.SERVER_PORT + 1,
            emotion_port=5005  # 情绪检测使用端口5005
        )
        
        # 初始化动作控制器
        motion_controller = MotionController(
            nao_ip=config.NAO_IP,
            nao_port=config.NAO_PORT
        )
        
        # 初始化阿里云音频播放器（先初始化，以便后续注册）
        aliyun_player = AliyunAudioPlayer(
            nao_ip=config.NAO_IP,
            nao_port=9561  # 使用固定端口9561（9559+2）接收TTS音频
        )
        
        # 注册阿里云播放器到音频录制器，实现协调
        try:
            audio_recorder.register_external_tts(aliyun_player)
            print("成功注册阿里云TTS播放器到音频录制器")
        except Exception as e:
            print("注册阿里云TTS播放器失败: " + str(e))
        
        # 启动音频录制线程
        audio_thread = threading.Thread(target=audio_recorder.recorder)
        audio_thread.daemon = True
        audio_thread.start()
        
        # 启动视频录制线程
        video_thread = threading.Thread(target=video_recorder.start_streaming)
        video_thread.daemon = True
        video_thread.start()
        
        # 启动网络客户端线程
        network_thread = threading.Thread(target=network_client.start)
        network_thread.daemon = True
        network_thread.start()
        
        # 存储所有资源，便于程序退出时清理
        resources = {
            'audio_recorder': audio_recorder,
            'video_recorder': video_recorder,
            'network_client': network_client,
            'motion_controller': motion_controller,
            'aliyun_player': aliyun_player
        }
        
        # 主循环
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n程序停止")
        # 清理资源
        cleanup(resources)
    except Exception as e:
        print("程序错误: " + str(e))
        # 尝试清理资源
        try:
            if 'resources' in locals():
                cleanup(resources)
        except Exception as e:
            print("清理资源时出错: " + str(e))

def cleanup(resources):
    """清理所有资源"""
    try:
        if 'video_recorder' in resources:
            print("停止视频录制...")
            resources['video_recorder'].stop_streaming()
        
        if 'audio_recorder' in resources:
            print("停止音频录制...")
            resources['audio_recorder'].stop_recording()
        
        if 'network_client' in resources:
            print("停止网络客户端...")
            resources['network_client'].stop()
            
        print("资源清理完成")
    except Exception as e:
        print("清理资源时出错: " + str(e))

if __name__ == "__main__":
    main() 