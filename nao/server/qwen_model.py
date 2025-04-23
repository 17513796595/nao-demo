import ollama
import socket
import time
from config import NAO_IP, NAO_PORT

class QwenModel:
    def __init__(self, nao_ip=NAO_IP, nao_port=NAO_PORT, system_prompt=None):
        self.nao_ip = nao_ip
        self.nao_port = nao_port
        self.system_prompt = system_prompt or """你是一个可爱、活泼的机器人助手。你的特点是：
1. 说话风格活泼可爱，经常使用"呢"、"呀"、"哦"等语气词
2. 对用户的问题充满好奇和热情
3. 回答简洁明了，不超过3句话
4. 在回答中不使用表情符号
5. 如果遇到不懂的问题，会诚实地表示不知道
6. 会主动关心用户的感受

请用这种风格回答用户的问题。"""
        
        # 情绪对应的提示词调整
        self.emotion_prompts = {
            "happy": "用户看起来很开心，请用更欢快的语气回应。",
            "sad": "用户看起来有些难过，请用更温柔和关心的语气回应。",
            "angry": "用户看起来有些生气，请用更平和的语气回应。",
            "neutral": "用户表情平静，请保持正常的活泼语气。",
            "surprise": "用户看起来有些惊讶，请用好奇的语气回应。",
            "fear": "用户看起来有些害怕，请用安抚的语气回应。",
            "disgust": "用户看起来有些厌恶，请用温和的语气回应。"
        }
        
        # 当前情绪状态
        self.current_emotion = "neutral"
    
    def update_emotion(self, emotion):
        """更新当前情绪状态"""
        self.current_emotion = emotion
    
    def get_emotion_prompt(self):
        """根据当前情绪获取对应的提示词"""
        if self.current_emotion in self.emotion_prompts:
            return self.emotion_prompts[self.current_emotion]
        return ""
    
    def call(self, text):
        """使用ollama库调用本地的Qwen模型，使用流式输出"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                print("Qwen正在回复: ", end='', flush=True)
                full_response = ""
                buffer = ""  # 用于缓存文本，在遇到标点符号时发送
                
                # 创建与NAO的UDP连接
                nao_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                # 将system_prompt和情绪提示词添加到提示词中
                emotion_prompt = self.get_emotion_prompt()
                full_prompt = f"{self.system_prompt}\n\n{emotion_prompt}\n\n用户说：{text}"
                
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
                        # 发送当前完整句子到NAO
                        try:
                            nao_socket.sendto(buffer.encode('utf-8'), (self.nao_ip, self.nao_port))
                            buffer = ""  # 清空缓存
                        except Exception as e:
                            print(f"\n发送到NAO失败: {str(e)}")
                            break
                
                # 发送剩余的文本（如果有）
                if buffer:
                    try:
                        nao_socket.sendto(buffer.encode('utf-8'), (self.nao_ip, self.nao_port))
                    except Exception as e:
                        print(f"\n发送剩余文本到NAO失败: {str(e)}")
                        
                print()  # 换行
                nao_socket.close()
                return full_response
                
            except Exception as e:
                print(f"\n调用Qwen模型出错 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    print(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    return f"调用Qwen模型出错: {str(e)}" 