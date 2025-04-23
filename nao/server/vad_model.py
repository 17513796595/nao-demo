import torch
import torchaudio
import numpy as np

class VADModel:
    def __init__(self):
        # 加载 Silero VAD 模型
        self.model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False
        )
        self.get_speech_ts = utils[0]
        self.save_audio = utils[2]
        self.read_audio = utils[3]
        self.VADIterator = utils[4]
        
    def preprocess_audio(self, audio_data):
        """预处理音频数据"""
        try:
            # 检查音频数据是否为空
            if audio_data is None or len(audio_data) == 0:
                print("警告：接收到空的音频数据")
                return None
                
            # 确保音频数据是float32类型
            audio_data = audio_data.astype(np.float32)
            
            # 归一化（添加安全检查）
            max_abs_value = np.max(np.abs(audio_data))
            if max_abs_value > 0:  # 防止除以零
                audio_data = audio_data / max_abs_value
            else:
                print("警告：音频数据全为零")
                return None
            
            # 转换为PyTorch张量
            audio_tensor = torch.from_numpy(audio_data).unsqueeze(0)
            
            # 检查音频长度
            if len(audio_data) < 2:  # 确保音频长度至少为2
                print("警告：音频数据太短，无法处理")
                return None
            
            # 重采样到16kHz（如果需要）
            if audio_tensor.shape[1] != 16000:
                resampler = torchaudio.transforms.Resample(
                    orig_freq=audio_tensor.shape[1],
                    new_freq=16000
                )
                audio_tensor = resampler(audio_tensor)
            
            return audio_tensor
        except Exception as e:
            print(f"音频预处理错误: {str(e)}")
            return None

def is_speech(audio_data, vad_model):
    """使用 Silero VAD 进行语音活动检测"""
    try:
        # 检查音频数据是否有效
        if audio_data is None or len(audio_data) == 0:
            print("警告：VAD接收到无效音频数据")
            return False
            
        # 预处理音频数据
        audio_tensor = vad_model.preprocess_audio(audio_data)
        if audio_tensor is None:
            return False
            
        # 检查音频张量长度
        if audio_tensor.shape[1] < 2:
            print("警告：预处理后的音频张量太短")
            return False
            
        # 使用 Silero VAD 进行检测
        try:
            speech_timestamps = vad_model.get_speech_ts(
                audio_tensor[0],
                vad_model.model,
                sampling_rate=16000,
                threshold=0.05
            )
            
            # 如果有语音片段，返回True
            return len(speech_timestamps) > 0
        except Exception as e:
            print(f"VAD模型检测错误: {str(e)}")
            return False
            
    except Exception as e:
        print(f"VAD检测错误: {str(e)}")
        return False 