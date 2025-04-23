#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import ollama
from qwen_model import QwenModel
from aliyun_tts import AliyunTTS
from config import NAO_IP, NAO_PORT

class AliyunQwenTTS:
    """
    整合Qwen模型和阿里云TTS的类
    使用Qwen生成文本，然后通过阿里云TTS转换为语音发送给NAO
    """
    def __init__(self, nao_ip=NAO_IP, nao_port=NAO_PORT):
        self.nao_ip = nao_ip
        self.nao_port = nao_port
        
        # 初始化Qwen模型
        self.qwen_model = QwenModel(nao_ip=nao_ip, nao_port=nao_port)
        
        # 初始化阿里云TTS，使用新的端口
        self.tts = AliyunTTS(nao_ip=nao_ip, nao_port=nao_port+2)
        
    def chat(self, text):
        """
        处理用户输入，生成响应并通过TTS播放
        """
        try:
            print("Qwen正在回复: ", end='', flush=True)
            full_response = ""
            buffer = ""  # 用于缓存文本，在遇到标点符号时发送
            
            # 将system_prompt和情绪提示词添加到提示词中
            emotion_prompt = self.qwen_model.get_emotion_prompt()
            full_prompt = f"{self.qwen_model.system_prompt}\n\n{emotion_prompt}\n\n用户说：{text}"
            
            # 调用Qwen模型生成回复
            for chunk in ollama.generate(
                model='qwen2.5:1.5b',
                prompt=full_prompt,
                stream=True
            ):
                response_piece = chunk['response']
                print(response_piece, end='', flush=True)
                full_response += response_piece
                
                # 累积文本到缓存
                buffer += response_piece
                
                # 检查是否有标点符号（句子结束标志）
                if any(p in buffer for p in ["。", "！", "？", ".", "!", "?", "\n"]):
                    # 处理当前完整句子，通过阿里云TTS合成
                    self.tts.synthesize(buffer)
                    buffer = ""  # 清空缓存
            
            # 处理剩余的文本（如果有）
            if buffer.strip():
                self.tts.synthesize(buffer)
                
            print()  # 换行
            return full_response
            
        except Exception as e:
            error_msg = f"调用模型出错: {str(e)}"
            print(error_msg)
            return error_msg
    
    def update_emotion(self, emotion):
        """
        更新情绪状态
        """
        self.qwen_model.update_emotion(emotion)

def main():
    """
    主函数，用于测试功能
    """
    # 检查环境变量是否设置
    if not os.environ.get('ALIYUN_ACCESS_KEY_ID'):
        print("警告: 未设置ALIYUN_ACCESS_KEY_ID环境变量")
    if not os.environ.get('ALIYUN_ACCESS_KEY_SECRET'):
        print("警告: 未设置ALIYUN_ACCESS_KEY_SECRET环境变量")
    if not os.environ.get('ALIYUN_APP_KEY'):
        print("警告: 未设置ALIYUN_APP_KEY环境变量")
    
    print("初始化AliyunQwenTTS...")
    aliyun_qwen = AliyunQwenTTS()
    
    # 简单的交互循环
    try:
        while True:
            user_input = input("\n请输入您的问题 (输入'exit'退出): ")
            if user_input.lower() in ['exit', 'quit', '退出']:
                break
                
            if user_input.strip():
                aliyun_qwen.chat(user_input)
    except KeyboardInterrupt:
        print("\n程序已退出")

if __name__ == "__main__":
    main() 