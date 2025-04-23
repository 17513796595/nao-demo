from funasr import AutoModel
import numpy as np
from queue import Queue
import threading
import librosa

class ASRModel:
    def __init__(self, model_path="/home/ye/.cache/modelscope/hub/models/iic/SenseVoiceSmall"):
        self.model = AutoModel(
            model=model_path,
            disable_update=True
        )
    
    def generate(self, audio_data):
        """生成语音识别结果"""
        try:
            # 添加预处理步骤
            audio_data = self._preprocess_audio(audio_data)
            text = self.model.generate(audio_data)
            return text[0]['text']
        except Exception as e:
            print(f"ASR识别错误: {str(e)}")
            return None

    def _preprocess_audio(self, audio_data):
        """音频预处理减少噪声"""
        # 降噪处理
        try:
            # 如果音频是字节数据，先转换
            if isinstance(audio_data, bytes):
                import io
                import soundfile as sf
                audio_data, _ = sf.read(io.BytesIO(audio_data))
            
            # 应用高通滤波器减少低频噪声
            audio_filtered = librosa.effects.preemphasis(audio_data)
            
            # 音量归一化
            audio_normalized = librosa.util.normalize(audio_filtered)
            
            return audio_normalized
        except:
            # 如果处理失败，返回原始数据
            return audio_data

def asr_worker(audio_data, result_queue, asr_model):
    """ASR识别工作线程"""
    try:
        text = asr_model.generate(audio_data)
        result_queue.put(('asr', text))
    except Exception as e:
        print(f"ASR识别错误: {str(e)}")
        result_queue.put(('asr', None)) 