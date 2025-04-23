# -*- coding: utf-8 -*-

import time
import math
from naoqi import ALProxy
import naoqi
import socket
import struct
import json

import config

class MotionController:
    def __init__(self, nao_ip=config.NAO_IP, nao_port=config.NAO_PORT):
        """初始化动作控制器"""
        try:
            # 初始化各个代理
            self.motion = ALProxy("ALMotion", nao_ip, nao_port)
            self.posture = ALProxy("ALRobotPosture", nao_ip, nao_port)
            self.awareness = ALProxy("ALBasicAwareness", nao_ip, nao_port)
            self.leds = ALProxy("ALLeds", nao_ip, nao_port)
            self.memory = ALProxy("ALMemory", nao_ip, nao_port)  # 添加内存代理
            self.tts = ALProxy("ALTextToSpeech", nao_ip, nao_port)  # 添加语音代理
            
            # 设置动作参数
            self.motion.setStiffnesses("Body", 1.0)
            self.motion.setStiffnesses("Arms", 1.0)
            self.motion.setStiffnesses("Legs", 1.0)
            
            # 设置动作速度
            self.speed = 0.3
            
            # 定义情绪对应的眼睛颜色
            self.emotion_colors = {
                "happy": [0.0, 1.0, 0.0],
                "sad": [0.0, 0.0, 1.0],
                "angry": [1.0, 0.0, 0.0],
                "neutral": [1.0, 1.0, 1.0],
                "surprise": [1.0, 1.0, 0.0],
                "fear": [0.5, 0.0, 0.5],
                "disgust": [0.5, 0.5, 0.0]
            }
            
            # 当前情绪状态
            self.current_emotion = "neutral"
            
            # 超声波测距参数
            self.distance_threshold = 0.5  # 距离阈值（米）
            self.is_moving = False  # 是否正在移动
            
            # 初始化NAO连接
            self.motion = ALProxy("ALMotion", nao_ip, nao_port)
            self.tts = ALProxy("ALTextToSpeech", nao_ip, nao_port)
            self.tts.setLanguage("Chinese")
            self.leds = ALProxy("ALLeds", nao_ip, nao_port)
            self.awareness = ALProxy("ALBasicAwareness", nao_ip, nao_port)
            self.memory = ALProxy("ALMemory", nao_ip, nao_port)
            self.posture = ALProxy("ALRobotPosture", nao_ip, nao_port)
            
            print("动作控制器初始化成功")
        except Exception as e:
            print("初始化动作控制器失败: %s" % str(e))
            raise
    
    def check_distance(self):
        """检查前方障碍物距离"""
        try:
            # 获取超声波传感器数据
            distance = self.memory.getData("Device/SubDeviceList/Platform/Front/Sonar/Sensor/Value")
            return distance
        except Exception as e:
            print("获取距离数据失败: %s" % str(e))
            return float('inf')  # 返回无穷大表示无法获取数据
    
    def speak(self, text):
        """让NAO说话"""
        try:
            self.tts.say(text)
            return True
        except Exception as e:
            print("语音输出失败: %s" % str(e))
            return False
    
    def _wait_for_motion(self):
        """等待动作完成"""
        time.sleep(0.1)
        while self.motion.moveIsActive():
            # 检查距离
            if self.is_moving:
                distance = self.check_distance()
                if distance < self.distance_threshold:
                    # 停止移动
                    self.motion.stopMove()
                    # 提示用户
                    self.speak("前面有物体，我停下来了")
                    self.is_moving = False
                    return False
            time.sleep(0.1)
        return True
    
    def walk_forward(self, distance=0.5):
        """向前走"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置移动标志
            self.is_moving = True
            
            # 执行前进动作
            self.motion.moveTo(distance, 0, 0, [
                ["MaxStepX", 0.04],
                ["MaxStepY", 0.14],
                ["MaxStepTheta", 0.1],
                ["MaxStepFrequency", 0.5],
                ["StepHeight", 0.02],
                ["TorsoWx", 0.0],
                ["TorsoWy", 0.0]
            ])
            
            # 等待动作完成，同时检查距离
            success = self._wait_for_motion()
            self.is_moving = False
            return success
        except Exception as e:
            print("前进动作失败: %s" % str(e))
            self.is_moving = False
            return False
    
    def walk_backward(self, distance=0.5):
        """向后走"""
        try:
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置移动标志
            self.is_moving = True
            
            self.motion.moveTo(-distance, 0, 0, [
                ["MaxStepX", 0.04],
                ["MaxStepY", 0.14],
                ["MaxStepTheta", 0.1],
                ["MaxStepFrequency", 0.5],
                ["StepHeight", 0.02],
                ["TorsoWx", 0.0],
                ["TorsoWy", 0.0]
            ])
            
            # 等待动作完成
            success = self._wait_for_motion()
            self.is_moving = False
            return success
        except Exception as e:
            print("后退动作失败: %s" % str(e))
            self.is_moving = False
            return False
    
    def set_emotion(self, emotion):
        """设置情绪并改变眼睛颜色
        Args:
            emotion: 情绪类型，必须是emotion_colors中定义的情绪之一
        """
        try:
            if emotion in self.emotion_colors:
                self.current_emotion = emotion
                color = self.emotion_colors[emotion]
                
                # 设置左右眼睛的颜色
                self.leds.fadeRGB("LeftFaceLeds", color[0], color[1], color[2], 0.5)
                self.leds.fadeRGB("RightFaceLeds", color[0], color[1], color[2], 0.5)
                return True
            else:
                print("未知的情绪类型: %s" % emotion)
                return False
        except Exception as e:
            print("设置情绪颜色失败: %s" % str(e))
            return False
    
    def reset_eyes(self):
        """重置眼睛颜色为默认状态"""
        try:
            self.leds.reset("FaceLeds")
            return True
        except Exception as e:
            print("重置眼睛颜色失败: %s" % str(e))
            return False
    
    def turn_left(self, angle=30):
        """向左转
        Args:
            angle: 转向角度（度）
        """
        try:
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 将角度转换为弧度
            angle_rad = math.radians(angle)
            self.motion.moveTo(0, 0, angle_rad, [
                ["MaxStepX", 0.04],
                ["MaxStepY", 0.14],
                ["MaxStepTheta", 0.1],
                ["MaxStepFrequency", 0.5],
                ["StepHeight", 0.02],
                ["TorsoWx", 0.0],
                ["TorsoWy", 0.0]
            ])
            self._wait_for_motion()
            return True
        except Exception as e:
            print("左转动作失败: %s" % str(e))
            return False
    
    def turn_right(self, angle=30):
        """向右转
        Args:
            angle: 转向角度（度）
        """
        try:
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 将角度转换为弧度，注意右转为负角度
            angle_rad = math.radians(-angle)
            self.motion.moveTo(0, 0, angle_rad, [
                ["MaxStepX", 0.04],
                ["MaxStepY", 0.14],
                ["MaxStepTheta", 0.1],
                ["MaxStepFrequency", 0.5],
                ["StepHeight", 0.02],
                ["TorsoWx", 0.0],
                ["TorsoWy", 0.0]
            ])
            self._wait_for_motion()
            return True
        except Exception as e:
            print("右转动作失败: %s" % str(e))
            return False
    
    def stop(self):
        """停止所有动作"""
        try:
            self.motion.stopMove()
            return True
        except Exception as e:
            print("停止动作失败: %s" % str(e))
            return False
    
    def stand_up(self):
        """站起来"""
        try:
            self.posture.goToPosture("StandInit", self.speed)
            return True
        except Exception as e:
            print("站立动作失败: %s" % str(e))
            return False
    
    def sit_down(self):
        """坐下"""
        try:
            self.posture.goToPosture("Sit", self.speed)
            return True
        except Exception as e:
            print("坐下动作失败: %s" % str(e))
            return False
    
    def wave(self):
        """挥手"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置手臂刚度
            self.motion.setStiffnesses("LArm", 1.0)
            self.motion.setStiffnesses("RArm", 1.0)
            
            # 执行挥手动作
            self.motion.angleInterpolation(
                ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
                [0.5, -0.2, 1.0, 0.5, 0.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                True
            )
            
            # 重复挥手动作
            for _ in range(3):
                self.motion.angleInterpolation(
                    ["RWristYaw"],
                    [1.0],
                    [0.5],
                    True
                )
                time.sleep(0.5)
                self.motion.angleInterpolation(
                    ["RWristYaw"],
                    [-1.0],
                    [0.5],
                    True
                )
                time.sleep(0.5)
            
            # 恢复初始姿势
            self.posture.goToPosture("StandInit", self.speed)
            return True
        except Exception as e:
            print("挥手动作失败: %s" % str(e))
            return False
    
    def nod(self):
        """点头"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置头部刚度
            self.motion.setStiffnesses("Head", 1.0)
            
            # 执行点头动作
            for _ in range(3):
                self.motion.angleInterpolation(
                    ["HeadPitch"],
                    [0.3],
                    [0.3],
                    True
                )
                time.sleep(0.3)
                self.motion.angleInterpolation(
                    ["HeadPitch"],
                    [-0.1],
                    [0.3],
                    True
                )
                time.sleep(0.3)
            
            return True
        except Exception as e:
            print("点头动作失败: %s" % str(e))
            return False
    
    def shake_head(self):
        """摇头"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置头部刚度
            self.motion.setStiffnesses("Head", 1.0)
            
            # 执行摇头动作
            for _ in range(3):
                self.motion.angleInterpolation(
                    ["HeadYaw"],
                    [0.5],
                    [0.3],
                    True
                )
                time.sleep(0.3)
                self.motion.angleInterpolation(
                    ["HeadYaw"],
                    [-0.5],
                    [0.3],
                    True
                )
                time.sleep(0.3)
            
            # 恢复头部位置
            self.motion.angleInterpolation(
                ["HeadYaw"],
                [0.0],
                [0.3],
                True
            )
            return True
        except Exception as e:
            print("摇头动作失败: %s" % str(e))
            return False
    
    def raise_hand(self):
        """举手"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置手臂刚度
            self.motion.setStiffnesses("LArm", 1.0)
            self.motion.setStiffnesses("RArm", 1.0)
            
            # 执行举手动作
            self.motion.angleInterpolation(
                ["RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
                [-1.0, -0.2, 1.0, 0.5, 0.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                True
            )
            
            time.sleep(2.0)  # 保持举手姿势
            
            # 恢复初始姿势
            self.posture.goToPosture("StandInit", self.speed)
            return True
        except Exception as e:
            print("举手动作失败: %s" % str(e))
            return False
    
    def clap(self):
        """鼓掌"""
        try:
            # 确保机器人处于站立状态
            self.posture.goToPosture("StandInit", self.speed)
            time.sleep(0.5)
            
            # 设置手臂刚度
            self.motion.setStiffnesses("LArm", 1.0)
            self.motion.setStiffnesses("RArm", 1.0)
            
            # 准备鼓掌姿势
            self.motion.angleInterpolation(
                ["LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "LWristYaw",
                 "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "RWristYaw"],
                [-0.5, 0.2, -1.0, -0.5, 0.0,
                 -0.5, -0.2, 1.0, 0.5, 0.0],
                [1.0, 1.0, 1.0, 1.0, 1.0,
                 1.0, 1.0, 1.0, 1.0, 1.0],
                True
            )
            
            # 执行鼓掌动作
            for _ in range(3):
                # 合掌
                self.motion.angleInterpolation(
                    ["LShoulderRoll", "RShoulderRoll"],
                    [0.4, -0.4],
                    [0.2],
                    True
                )
                time.sleep(0.2)
                # 分开
                self.motion.angleInterpolation(
                    ["LShoulderRoll", "RShoulderRoll"],
                    [0.2, -0.2],
                    [0.2],
                    True
                )
                time.sleep(0.2)
            
            # 恢复初始姿势
            self.posture.goToPosture("StandInit", self.speed)
            return True
        except Exception as e:
            print("鼓掌动作失败: %s" % str(e))
            return False

if __name__ == "__main__":
    # 测试代码
    try:
        controller = MotionController()
        print("开始测试动作...")
        
        # 测试各个动作
        controller.stand_up()
        time.sleep(1)
        
        controller.walk_forward(0.5)
        time.sleep(1)
        
        controller.turn_left(30)
        time.sleep(1)
        
        controller.wave()
        time.sleep(1)
        
        controller.nod()
        time.sleep(1)
        
        controller.shake_head()
        time.sleep(1)
        
        controller.raise_hand()
        time.sleep(1)
        
        controller.clap()
        time.sleep(1)
        
        controller.walk_backward(0.5)
        time.sleep(1)
        
        controller.sit_down()
        
        print("动作测试完成")
    except Exception as e:
        print("测试过程中出现错误: %s" % str(e))