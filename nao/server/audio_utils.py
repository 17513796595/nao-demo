import numpy as np
import io
import wave
from queue import Queue
import threading
from vad_model import is_speech

def is_valid_text(text, is_speech_result):
    """检测文本是否有效，同时考虑VAD结果"""
    # 去除空白字符
    text = text.strip()
    
    # 检查文本是否为空或只包含标点符号
    if not text or all(c in '，。！？,.!?' for c in text):
        print("文本无效：为空或只包含标点符号")
        return False
        
    # 只有当VAD检测为语音且文本有效时才返回True
    if not is_speech_result:
        print("VAD检测未通过")
    else:
        print("VAD检测通过")
        
    return is_speech_result

def vad_worker(audio_data, result_queue, vad_model):
    """VAD检测工作线程"""
    try:
        is_speech_result = is_speech(audio_data, vad_model)
        result_queue.put(('vad', is_speech_result))
    except Exception as e:
        print(f"VAD检测错误: {str(e)}")
        result_queue.put(('vad', False))

def process_audio_data(data):
    """处理音频数据"""
    try:
        # 检查数据是否为空
        if data is None or len(data) == 0:
            print("警告：接收到空的音频数据包")
            return None
            
        # 将接收到的音频数据包装成io.BytesIO流
        audio_stream = io.BytesIO(data)
        
        # 使用wave模块读取音频数据流
        with wave.open(audio_stream, "rb") as wf:
            # 获取帧数
            nframes = wf.getnframes()
            if nframes == 0:
                print("警告：音频文件没有帧")
                return None
                
            frames = wf.readframes(nframes)
            audio_data = np.frombuffer(frames, dtype=np.int16)
            
            # 检查处理后的数据
            if len(audio_data) == 0:
                print("警告：处理后的音频数据为空")
                return None
        
        return audio_data.astype(np.float32)
    except Exception as e:
        print(f"处理音频数据错误: {e}")
        return None 