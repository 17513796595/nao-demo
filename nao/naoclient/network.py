# -*- coding: utf-8 -*-
import socket
import struct
import json
import time
import threading
from motion_controller import MotionController
import config

class NetworkManager(object):
    def __init__(self, server_ip, server_port):
        self.SERVER_IP = server_ip
        self.SERVER_PORT = server_port
        self.socket = None
        self.motion_controller = MotionController()
        
    def create_socket(self):
        """创建UDP socket"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        return self.socket
        
    def send_data(self, data):
        """发送数据到服务器"""
        try:
            # 分片大小（1400字节，留出一些空间给UDP头部）
            chunk_size = 1400
            total_chunks = (len(data) + chunk_size - 1) // chunk_size
            
            # 发送文件头信息
            header = struct.pack('!I', total_chunks)
            self.socket.sendto(header, (self.SERVER_IP, self.SERVER_PORT))
            
            # 分片发送数据
            for i in range(total_chunks):
                start = i * chunk_size
                end = min(start + chunk_size, len(data))
                chunk = data[start:end]
                
                # 添加分片头部信息
                chunk_header = struct.pack('!I', i)
                chunk_with_header = chunk_header + chunk
                
                self.socket.sendto(chunk_with_header, (self.SERVER_IP, self.SERVER_PORT))
                
            return True
        except Exception as e:
            print("发送数据错误: " + str(e))
            return False
    
    def receive_command(self):
        """接收并处理来自服务器的指令"""
        try:
            # 设置超时时间为1秒
            self.socket.settimeout(3.0)
            
            # 接收数据
            data, addr = self.socket.recvfrom(65536)
            # 使用更安全的编码处理方式
            try:
                command = data.decode('utf-8')
            except UnicodeDecodeError:
                command = data
            
            # 尝试解析JSON格式的指令
            try:
                command_data = json.loads(command)
                if "type" in command_data:
                    # 如果是speech类型指令，跳过处理（由阿里云TTS处理）
                    if command_data["type"] == "speech":
                        print("收到语音指令，由阿里云TTS处理")
                        return True
                        
                    # 只处理情绪状态指令，不处理带语音的情绪指令
                    elif command_data["type"] == "emotion_state":
                        # 处理情绪指令
                        if "emotion" in command_data:
                            self.motion_controller.set_emotion(command_data["emotion"])
                            return True
                    
                    elif command_data["type"] == "motion":
                        # 处理动作指令
                        if "action" in command_data:
                            command = command_data["action"]
                        else:
                            return False
                            
                    # 处理MP3播放指令
                    elif command_data["type"] == "play_mp3" and "file_path" in command_data:
                        try:
                            # 使用NAO的音频播放服务播放MP3
                            file_path = command_data["file_path"]
                            print("播放音频文件:"+str(file_path))
                            self.motion_controller.play_audio_file(file_path)
                            return True
                        except Exception as e:
                            print("播放MP3文件出错: "+str(e))
                            return False
            except json.JSONDecodeError:
                # 如果不是JSON格式，按原来的方式处理
                pass
            
            # 处理动作指令
            if command == "walk_forward":
                self.motion_controller.walk_forward(0.5)
            elif command == "walk_backward":
                self.motion_controller.walk_backward(0.5)
            elif command == "turn_left":
                self.motion_controller.turn_left(30)
            elif command == "turn_right":
                self.motion_controller.turn_right(30)
            elif command == "stop":
                self.motion_controller.stop()
            elif command == "stand_up":
                self.motion_controller.stand_up()
            elif command == "sit_down":
                self.motion_controller.sit_down()
            elif command == "wave":
                self.motion_controller.wave()
            elif command == "nod":
                self.motion_controller.nod()
            elif command == "shake_head":
                self.motion_controller.shake_head()
            elif command == "raise_hand":
                self.motion_controller.raise_hand()
            elif command == "clap":
                self.motion_controller.clap()
            elif command == "reset_eyes":
                self.motion_controller.reset_eyes()
            
            return True
        except socket.timeout:
            # 超时，继续等待
            return False
        except Exception as e:
            print("处理指令错误:" + str(e))
            return False
            
    def close(self):
        """关闭socket连接"""
        if self.socket:
            self.socket.close()

# 新增NetworkClient类供main.py调用
class NetworkClient(NetworkManager):
    def __init__(self, server_ip=config.SERVER_IP, server_port=config.SERVER_PORT):
        """初始化网络客户端"""
        super(NetworkClient, self).__init__(server_ip, server_port)
        self.is_running = False
        self.create_socket()
        print("网络客户端已初始化，服务器地址: " + str(server_ip) + ":" + str(server_port))
    
    def start(self):
        """启动网络客户端，持续监听命令"""
        self.is_running = True
        print("网络客户端启动，等待接收命令...")
        
        while self.is_running:
            try:
                # 接收命令
                self.receive_command()
                time.sleep(0.1)  # 避免占用过多CPU资源
            except Exception as e:
                print("网络客户端运行错误: " + str(e))
                time.sleep(1)  # 出错后暂停一段时间再继续
    
    def stop(self):
        """停止网络客户端"""
        self.is_running = False
        self.close()
        print("网络客户端已停止")
