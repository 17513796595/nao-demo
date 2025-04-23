import socket
import re
import json
import time
import threading
from object_detector import ObjectDetector
from config import NAO_IP, NAO_PORT
from aliyun_tts import AliyunTTS  # 导入阿里云TTS
from qwen_model import QwenModel
from emotion_detector import EmotionDetector

class CommandHandler:
    def __init__(self, nao_ip=NAO_IP, nao_port=NAO_PORT):
        """初始化命令处理器
        
        Args:
            nao_ip: NAO机器人IP地址
            nao_port: NAO机器人端口
        """
        self.nao_ip = nao_ip
        self.nao_port = nao_port
        
        # 初始化物体检测器
        self.object_detector = ObjectDetector(nao_ip=nao_ip, nao_port=nao_port)
        
        # 初始化情绪检测器
        self.emotion_detector = EmotionDetector()
        
        # 初始化文本转语音
        self.tts = AliyunTTS()
        
        # 初始化大模型
        self.qwen_model = QwenModel()
        
        # 创建UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # 命令模式
        self.COMMAND_PATTERNS = {
            # 运动命令
            "前进|向前走": "walk_forward",
            "后退|向后走": "walk_backward",
            "左转": "turn_left",
            "右转": "turn_right",
            "停止|停下": "stop",
            "站起来": "stand_up",
            "坐下": "sit_down",
            "摆手|挥手": "wave",
            "点头": "nod",
            "摇头": "shake_head",
            "举手": "raise_hand",
            "鼓掌": "clap",
            
            # 情绪命令
            "开心|高兴": "happy",
            "伤心|难过": "sad",
            "生气|愤怒": "angry",
            "害怕|恐惧": "fear",
            "惊讶": "surprise",
            "正常|重置|复位": "reset",
            
            # 物体检测命令
            "看看周围|你看到了什么|你能看到什么": "detect_objects",
            
            # 大模型交互
            "你知道|你认为|你觉得|请问|是什么|为什么": "qwen_query"
        }
        
        # 启动物体检测线程
        self.object_detector.start_nao_video_receiver()
        
        print("命令处理器初始化成功")
    
    def process_command(self, command):
        """处理命令
        
        Args:
            command: 接收到的命令文本
            
        Returns:
            response: 命令处理结果
        """
        try:
            # 查找匹配的命令模式
            found_pattern = False
            command_type = None
            
            # 大模型查询特殊处理
            if re.search(self.COMMAND_PATTERNS["你知道|你认为|你觉得|请问|是什么|为什么"], command):
                return self.handle_qwen_query(command)
            
            # 物体检测特殊处理
            if re.search(self.COMMAND_PATTERNS["看看周围|你看到了什么|你能看到什么"], command):
                return self.handle_object_detection()
            
            # 处理其他命令
            for pattern, cmd_type in self.COMMAND_PATTERNS.items():
                if re.search(pattern, command):
                    found_pattern = True
                    command_type = cmd_type
                    break
            
            if found_pattern:
                # 根据命令类型处理
                if command_type in ["happy", "sad", "angry", "fear", "surprise", "reset"]:
                    # 情绪命令
                    return self.handle_emotion_command(command_type)
                else:
                    # 动作命令
                    return self.handle_motion_command(command_type)
            else:
                # 未匹配到命令，转给大模型处理
                return self.handle_qwen_query(command)
        
        except Exception as e:
            print(f"处理命令出错: {str(e)}")
            return f"处理命令出错: {str(e)}"
    
    def handle_motion_command(self, command_type):
        """处理动作命令
        
        Args:
            command_type: 命令类型
            
        Returns:
            response: 命令处理结果
        """
        try:
            # 构建命令
            command = {
                "type": "motion",
                "action": command_type
            }
            
            # 发送命令
            self.send_command_to_nao(command)
            
            return f"执行{command_type}动作"
        except Exception as e:
            print(f"处理动作命令出错: {str(e)}")
            return f"处理动作命令出错: {str(e)}"
    
    def handle_emotion_command(self, emotion_type):
        """处理情绪命令
        
        Args:
            emotion_type: 情绪类型
            
        Returns:
            response: 命令处理结果
        """
        try:
            # 构建命令
            command = {
                "type": "emotion",
                "emotion": emotion_type
            }
            
            # 发送命令
            self.send_command_to_nao(command)
            
            return f"设置情绪为{emotion_type}"
        except Exception as e:
            print(f"处理情绪命令出错: {str(e)}")
            return f"处理情绪命令出错: {str(e)}"
    
    def handle_object_detection(self):
        """处理物体检测命令
        
        Returns:
            response: 检测结果描述
        """
        try:
            # 从NAO获取物体检测结果
            detected_objects = self.object_detector.detect_from_nao()
            
            # 格式化检测结果
            result = self.object_detector.format_detection_result(detected_objects)
            
            # 使用阿里云TTS合成语音
            self.tts.synthesize(result)
            
            return result
        except Exception as e:
            print(f"处理物体检测命令出错: {str(e)}")
            return f"处理物体检测命令出错: {str(e)}"
    
    def handle_qwen_query(self, query):
        """处理大模型查询
        
        Args:
            query: 查询文本
            
        Returns:
            response: 查询结果
        """
        try:
            # 首先合成一个简短的响应，让用户知道NAO正在思考
            thinking_response = "让我思考一下..."
            # 立即发送思考响应，增强用户体验
            self.tts.synthesize(thinking_response)
            
            # 异步调用大模型，避免长时间阻塞
            def async_model_call():
                try:
                    # 调用大模型获取回答
                    response = self.qwen_model.call(query)
                    
                    # 合成语音 - 使用HTTP方式，更快更简洁
                    self.tts.synthesize(response, use_ws=False)
                    
                    # 只在服务器端打印回复，但不返回给NAO
                    print(f"大模型回复: {response}")
                except Exception as e:
                    print(f"异步处理大模型查询出错: {str(e)}")
                    # 出错时发送错误提示
                    self.tts.synthesize(f"抱歉，我遇到了问题: {str(e)}", use_ws=False)
            
            # 创建并启动异步线程
            thread = threading.Thread(target=async_model_call)
            thread.daemon = True
            thread.start()
            
            # 返回空字符串表示不需要向NAO发送文本
            return ""
        except Exception as e:
            print(f"处理大模型查询出错: {str(e)}")
            return f"处理大模型查询出错: {str(e)}"
    
    def send_command_to_nao(self, command):
        """发送命令到NAO机器人
        
        Args:
            command: 命令字典
        """
        try:
            # 将命令转换为JSON
            command_json = json.dumps(command)
            
            # 发送命令
            self.socket.sendto(command_json.encode('utf-8'), (self.nao_ip, self.nao_port))
        except Exception as e:
            print(f"发送命令到NAO出错: {str(e)}")
            raise
    
    def __del__(self):
        """析构函数，关闭资源"""
        try:
            # 关闭物体检测线程
            if hasattr(self, 'object_detector'):
                self.object_detector.stop_nao_video_receiver()
            
            # 关闭socket
            if hasattr(self, 'socket'):
                self.socket.close()
        except Exception as e:
            print(f"关闭资源出错: {str(e)}")