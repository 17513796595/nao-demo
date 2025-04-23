# -*- coding: utf-8 -*-
import time
import naoqi
from naoqi import ALProxy
import threading
import Queue
import socket
import struct
import re
import hashlib

import config

class AudioRecorder:
    def __init__(self, nao_ip=config.NAO_IP, nao_port=config.NAO_PORT, server_ip=config.SERVER_IP, server_port=config.SERVER_PORT):
        # 初始化NAO连接
        self.NAO_IP = nao_ip
        self.NAO_PORT = nao_port
        
        # 服务器配置
        self.SERVER_IP = server_ip
        self.SERVER_PORT = server_port
        
        # 录音参数
        self.ENERGY_THRESHOLD = 17000  # 能量阈值，检测声音的灵敏度
        self.record_path = "/home/nao/naoqi/audio.wav"
        
        # 日志控制变量
        self.last_energy_log_time = 0  # 上次记录低能量的时间
        self.last_speech_log_time = 0  # 上次记录检测到声音的时间
        self.log_interval = 2.0  # 日志记录间隔（秒）
        
        # 初始化录音设备
        try:
            self.audio_device = ALProxy("ALAudioDevice", nao_ip, nao_port)
            self.audio_recorder = ALProxy("ALAudioRecorder", nao_ip, nao_port)
            self.tts = ALProxy("ALTextToSpeech", nao_ip, nao_port)
            self.aup = ALProxy("ALAudioPlayer", nao_ip, nao_port)
            print("音频设备初始化成功")
        except Exception as e:
            print("初始化音频设备失败: " + str(e))
            return
            
        # 文本播放队列
        self.text_queue = Queue.Queue()
        
        # 创建应答接收socket
        self.response_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.response_socket.bind(("0.0.0.0", server_port))
        
        # 设置接收缓冲区大小
        self.response_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        
        # 启动接收响应的线程
        self.receiver_thread = threading.Thread(target=self.receive_response)
        self.receiver_thread.daemon = True
        self.receiver_thread.start()
        
        # 启动TTS播放线程
        self.tts_thread = threading.Thread(target=self.process_tts_queue)
        self.tts_thread.daemon = True
        self.tts_thread.start()
        
        # TTS状态标志
        self.is_tts_playing = False
        
        # 添加外部TTS播放状态 - 用于检查阿里云TTS是否在播放
        self.external_tts_playing = False
        
        # 录音状态
        self.is_recording = False
        
        self.energy_samples = []
        self.calibration_period = 300  # 每300次采样重新校准一次
        self.sample_count = 0
        self.adaptive_threshold_multiplier = 1.5  # 背景噪声的1.5倍作为阈值
        
        print("音频录制器初始化成功")
    
    def is_tts_busy(self):
        """检查TTS是否正在播放"""
        try:
            return self.tts.isSpeaking()
        except:
            return False
            
    def register_external_tts(self, aliyun_player):
        """注册外部TTS播放器，用于协调录音和播放"""
        try:
            self.aliyun_player = aliyun_player
            
            # 使用定时轮询方式监控播放状态
            def monitor_playing_state():
                while True:
                    try:
                        # 直接访问属性
                        old_state = self.external_tts_playing
                        self.external_tts_playing = aliyun_player.is_playing
                        
                        # 只在状态变化时记录日志
                        if old_state != self.external_tts_playing:
                            print("AliyunTTS播放状态更新: %s -> %s" % (old_state, self.external_tts_playing))
                    except:
                        pass
                    time.sleep(0.5)  # 每0.5秒检查一次
            
            # 启动监控线程
            self.monitor_thread = threading.Thread(target=monitor_playing_state)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            
            print("成功注册外部TTS播放器")
        except Exception as e:
            print("注册外部TTS播放器失败: " + str(e))
    
    def should_pause_recording(self):
        """判断是否应该暂停录音"""
        return self.is_tts_playing or self.external_tts_playing or self.is_tts_busy()
        
    def process_tts_queue(self):
        """处理TTS播放队列"""
        while True:
            try:
                # 从队列获取文本
                text = self.text_queue.get()
                if text:
                    # 确保text是NAO TTS需要的格式
                    if isinstance(text, unicode):
                        text = text.encode('utf-8')  # 转换unicode为utf-8字符串
                    
                    # 处理标点符号（为了避免TTS读出标点符号）
                    # 中文常见标点符号和英文标点符号
                    self.is_tts_playing = True
                    self.tts.say(text)
                    # 等待TTS播放完成
                    while self.is_tts_busy():
                        time.sleep(0.1)
                    self.is_tts_playing = False
            except Exception as e:
                print("TTS播放错误: " + str(e))
                time.sleep(0.1)
    
    
    def receive_response(self):
        """接收并播放PC返回的文本响应"""
        print("等待接收文本响应...")
        while True:
            try:
                data, addr = self.response_socket.recvfrom(65536)
                if not data:
                    continue
                    
                # 为了避免处理二进制数据，我们完全禁用文本处理
                # 此方法仍然保留，但不再处理任何接收到的数据
                print("收到数据，但已禁用文本处理")
                    
            except Exception as e:
                print("接收响应错误: " + str(e))
                time.sleep(1)
    def calculate_checksum(self, data):
        """计算数据的MD5校验和"""
        return hashlib.md5(data).hexdigest()

    def send_to_server(self, file_path):
        try:
            time.sleep(0.1)
            file_path = "/home/nao/naoqi/audio.wav"

            try:
                with open(file_path, "rb") as f:
                    audio_data = f.read()
                    print("成功读取")
            except Exception as e:
                print("读取文件失败:" + str(e))
                return
                
            # 计算校验和
            checksum = self.calculate_checksum(audio_data)
            print("文件校验和: %s" % checksum)
            
            # 创建UDP socket发送文件
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # 设置发送缓冲区大小
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                
                # 分片大小（1400字节，留出一些空间给UDP头部）
                chunk_size = 1400
                total_chunks = (len(audio_data) + chunk_size - 1) // chunk_size
                
                # 生成唯一会话ID
                session_id = int(time.time() * 1000) % 1000000
                
                # 发送头信息(会话ID, 总分片数, 校验和长度, 校验和)
                header = struct.pack('!III', session_id, total_chunks, len(checksum))
                header_with_checksum = header + checksum.encode('utf-8')
                s.sendto(header_with_checksum, (self.SERVER_IP, self.SERVER_PORT))
                
                # 设置超时
                s.settimeout(0.5)
                
                # 等待会话确认
                try:
                    ack_data, addr = s.recvfrom(1024)
                    ack_session_id = struct.unpack('!I', ack_data)[0]
                    if ack_session_id != session_id:
                        print("会话ID不匹配，通信可能有问题")
                        return
                except socket.timeout:
                    print("等待会话确认超时，继续发送")
                
                # 跟踪已确认的块
                confirmed_chunks = set()
                
                # 分片发送数据
                for i in range(total_chunks):
                    start = i * chunk_size
                    end = min(start + chunk_size, len(audio_data))
                    chunk = audio_data[start:end]
                    
                    # 添加分片头部信息（会话ID+分片索引）
                    chunk_header = struct.pack('!II', session_id, i)
                    chunk_with_header = chunk_header + chunk
                    
                    max_retries = 3
                    retry_count = 0
                    
                    while i not in confirmed_chunks and retry_count < max_retries:
                        s.sendto(chunk_with_header, (self.SERVER_IP, self.SERVER_PORT))
                        
                        # 每发送5个分片等待一次确认
                        if (i + 1) % 5 == 0 or i == total_chunks - 1:
                            try:
                                # 等待服务器确认
                                s.settimeout(0.5)
                                while True:
                                    try:
                                        ack_data, addr = s.recvfrom(1024)
                                        ack_session, ack_chunk = struct.unpack('!II', ack_data)
                                        if ack_session == session_id:
                                            confirmed_chunks.add(ack_chunk)
                                            # 如果所有最近的5个分片都已确认，跳出等待
                                            if all(x in confirmed_chunks for x in range(max(0, i-4), i+1)):
                                                break
                                    except socket.timeout:
                                        break
                            except Exception as e:
                                print("接收确认时出错: " + str(e))
                        
                        retry_count += 1
                        time.sleep(0.001)  # 短暂延迟
                    
                    # 每20个分片打印一次进度
                    if i % 20 == 0:
                        print("发送进度: %d/%d" % (i, total_chunks))
                
                # 发送完成后检查是否所有分片都已确认
                missing_chunks = [i for i in range(total_chunks) if i not in confirmed_chunks]
                if missing_chunks:
                    print("警告: %d 个分片未得到确认: %s" % (len(missing_chunks), missing_chunks[:5]))
                else:
                    print("所有分片已确认，文件发送成功")
                
            finally:
                s.close()
        except Exception as e:
            print("发送文件错误: " + str(e))
        
    def calibrate_threshold(self):
        """基于环境噪声重新计算能量阈值"""
        # 收集5秒的环境噪声样本
        calibration_samples = []
        print("校准环境噪声阈值...")
        for _ in range(50):  # 收集50个样本
            try:
                energy = self.audio_device.getFrontMicEnergy() * 100
                calibration_samples.append(energy)
                time.sleep(0.1)
            except Exception as e:
                print("校准时获取能量错误: " + str(e))
        
        if calibration_samples:
            # 计算噪声平均值和标准差
            avg_noise = sum(calibration_samples) / len(calibration_samples)
            # 新阈值 = 平均噪声 + 乘数 * 标准差
            self.ENERGY_THRESHOLD = avg_noise * self.adaptive_threshold_multiplier
            print("阈值校准完成: %.2f" % self.ENERGY_THRESHOLD)

    def get_average_energy(self):
        """带自适应阈值的能量获取函数"""
        energies = []
        for _ in range(3):
            try:
                energy = self.audio_device.getFrontMicEnergy() * 100
                energies.append(energy)
                self.energy_samples.append(energy)
                time.sleep(0.01)
            except Exception as e:
                print("获取能量错误: " + str(e))
                return 0
        
        # 定期更新阈值
        self.sample_count += 1
        if self.sample_count >= self.calibration_period:
            self.sample_count = 0
            # 使用最近的环境噪声样本更新阈值
            if len(self.energy_samples) > 100:
                # 取最小的100个样本作为背景噪声
                background = sorted(self.energy_samples)[:100]
                avg_background = sum(background) / len(background)
                self.ENERGY_THRESHOLD = avg_background * self.adaptive_threshold_multiplier
                print("阈值自动调整为: %.2f" % self.ENERGY_THRESHOLD)
                # 清空样本
                self.energy_samples = []
        
        return sum(energies) / len(energies) if energies else 0
        
    def recorder(self):
        buffer_size = 50  # 保存0.5秒的缓冲区(基于10ms的采样间隔)
        energy_buffer = []  # 能量缓冲区
        
        while True:
            try:
                # 如果TTS正在播放或外部TTS正在播放，暂停录音
                if self.should_pause_recording():
                    if self.is_recording:
                        print("TTS正在播放，暂停录音")
                        try:
                            self.audio_recorder.stopMicrophonesRecording()
                            self.is_recording = False
                        except:
                            pass
                    time.sleep(0.1)
                    continue
                
                # 初始停止录音
                if self.is_recording:
                    try:
                        self.audio_recorder.stopMicrophonesRecording()
                        self.is_recording = False
                    except:
                        pass
                
                time.sleep(0.2)
                wait = 0
                
                # 生成唯一文件名
                timestamp = int(time.time())
                unique_filename = "/home/nao/naoqi/audio_%d.wav" % timestamp
                
                # 开始录音(使用唯一文件名)
                try:
                    self.audio_recorder.startMicrophonesRecording(
                        unique_filename, "wav", 16000, (0, 0, 1, 0)
                    )
                    self.is_recording = True
                    current_recording_file = unique_filename  # 保存当前录音文件名
                    print("开始监听，录音保存到：%s" % unique_filename)
                    
                    # 记录录音开始时间
                    recording_start_time = time.time()
                except Exception as e:
                    print("开始录音失败: " + str(e))
                    time.sleep(1)
                    continue
                
                energy_buffer = []  # 清空缓冲区
                spoke_in_current_session = False
                
                while True:
                    # 获取当前能量
                    current_energy = self.get_average_energy()
                    current_time = time.time()
                    
                    # 检查是否超过最大录音时间(9秒)
                    if current_time - recording_start_time >= 9.0:
                        print("达到最大录音时间限制(9秒)，停止录音")
                        try:
                            self.audio_recorder.stopMicrophonesRecording()
                            self.is_recording = False
                            time.sleep(0.5)  # 确保文件写入完成
                            self.send_to_server(current_recording_file)
                        except Exception as e:
                            print("停止录音失败: " + str(e))
                        break
                    
                    # 添加到缓冲区
                    energy_buffer.append(current_energy)
                    if len(energy_buffer) > buffer_size:
                        energy_buffer.pop(0)  # 保持缓冲区大小固定
                    
                    # 检测是否有语音
                    if current_energy >= self.ENERGY_THRESHOLD:
                        # 如果是本次会话中第一次检测到语音且缓冲区已满
                        if not spoke_in_current_session and len(energy_buffer) == buffer_size:
                            print("检测到语音，包含预缓冲数据")
                        
                        # 标记已经说话
                        spoke_in_current_session = True
                        
                        # 检测到声音后开始计时
                        if not hasattr(self, 'speech_start_time'):
                            self.speech_start_time = time.time()
                        
                        # 计算连续说话时长
                        speech_duration = current_time - self.speech_start_time
                        
                        # 如果连续说话超过最大时长，分段保存发送
                        max_continuous_recording = 3.0
                        if speech_duration >= max_continuous_recording:
                            print("录音时长已达到%.1f秒，分段保存发送" % max_continuous_recording)
                            try:
                                # 停止当前录音
                                self.audio_recorder.stopMicrophonesRecording()
                                self.is_recording = False
                                
                                # 等待文件写入完成
                                time.sleep(0.2)
                                
                                # 发送音频数据
                                self.send_to_server(current_recording_file)
                                
                                # 重新开始录音
                                time.sleep(0.1)
                                self.audio_recorder.startMicrophonesRecording(
                                    current_recording_file, "wav", 16000, (0, 0, 1, 0)
                                )
                                self.is_recording = True
                                print("继续录音...")
                                
                                # 重置开始时间
                                self.speech_start_time = time.time()
                                # 更新总录音开始时间，确保不会超过总计9秒
                                recording_start_time = time.time()
                            except Exception as e:
                                print("分段录音失败: " + str(e))
                                self.is_recording = False
                                break

                    if current_energy < self.ENERGY_THRESHOLD:
                        wait += 0.1
                        
                        # 使用时间间隔控制，避免频繁打印噪音值
                        if current_time - self.last_energy_log_time >= self.log_interval:
                            print("当前能量: %.2f < %d" % (current_energy, self.ENERGY_THRESHOLD))
                            self.last_energy_log_time = current_time

                        if wait >= 1 and self.is_recording:
                            print("检测到语音结束，停止录音")
                            self.audio_recorder.stopMicrophonesRecording()
                            self.is_recording = False
                            time.sleep(0.5)  # 增加等待时间，确保文件写入完成
                            self.send_to_server(current_recording_file)
                            break
                    else:
                        wait = 0
                        
                        # 使用时间间隔控制，避免频繁打印声音能量值
                        if current_time - self.last_speech_log_time >= self.log_interval:
                            print("检测到声音！能量: %.2f" % current_energy)
                            self.last_speech_log_time = current_time
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                print("\n程序停止")
                try:
                    self.audio_recorder.stopMicrophonesRecording()
                    self.is_recording = False
                except:
                    pass
                break
                
            except Exception as e:
                print("录音错误: " + str(e))
                time.sleep(1)
                
    def stop_recording(self):
        """停止录音 - 用于程序退出时调用"""
        try:
            if self.is_recording:
                self.audio_recorder.stopMicrophonesRecording()
                self.is_recording = False
        except:
            pass
    
    def play_mp3(self, file_path):
        """播放指定路径的MP3文件"""
        try:
            print("播放MP3文件: %s" % file_path)
            self.aup.playFile(file_path)
        except Exception as e:
            print("播放MP3文件失败: " + str(e))