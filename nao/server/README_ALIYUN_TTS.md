# 阿里云TTS与Qwen集成使用指南

本模块实现了通过阿里云语音合成服务将Qwen生成的文本转换为高质量语音，并发送给NAO机器人播放。这是对现有功能的补充，不影响原有的直接文本通信功能。

## 功能特点

1. **高质量语音合成**：使用阿里云的专业语音合成服务，支持多种音色和参数调整
2. **流式处理**：实时将Qwen生成的文本转换为语音并发送给NAO
3. **完整句子处理**：基于标点符号分段处理文本，确保语音自然流畅
4. **原有功能不变**：可与现有的基于文本的交互并行使用
5. **独立通信通道**：使用独立端口进行音频数据传输，不干扰现有通信
6. **无特殊依赖**：使用标准HTTP请求调用阿里云API，不需要特殊依赖库

## 使用步骤

### 1. 配置阿里云访问密钥

首先，您需要获取阿里云的访问密钥和应用密钥，并设置环境变量：

```bash
export ALIYUN_ACCESS_KEY_ID="您的AccessKey"
export ALIYUN_ACCESS_KEY_SECRET="您的AccessKeySecret"
export ALIYUN_APP_KEY="您的应用密钥"
```

您可以使用以下命令临时设置这些环境变量：

```bash
# 临时设置环境变量
export ALIYUN_ACCESS_KEY_ID="您的AccessKey"
export ALIYUN_ACCESS_KEY_SECRET="您的AccessKeySecret"
export ALIYUN_APP_KEY="您的应用密钥"

# 验证设置是否成功
echo $ALIYUN_ACCESS_KEY_ID
echo $ALIYUN_ACCESS_KEY_SECRET
echo $ALIYUN_APP_KEY
```

建议将这些命令添加到`~/.bashrc`或`~/.profile`文件中，以便自动加载：

```bash
# 编辑.bashrc文件
nano ~/.bashrc

# 在文件末尾添加以下内容
export ALIYUN_ACCESS_KEY_ID="您的AccessKey"
export ALIYUN_ACCESS_KEY_SECRET="您的AccessKeySecret"
export ALIYUN_APP_KEY="您的应用密钥"

# 保存文件并退出编辑器
# 重新加载.bashrc
source ~/.bashrc
```

### 2. 安装依赖

确保已安装`requests`库：

```bash
pip install requests
```

### 3. 启动服务器端

您可以选择直接使用集成模式，或者单独测试阿里云TTS功能：

#### 测试阿里云TTS功能

```bash
cd server
python aliyun_tts.py
```

这将运行测试函数，合成一段示例文本"你好，我是一个测试语音。今天天气真不错！你觉得呢？"

#### 使用Qwen+阿里云TTS集成模式

```bash
cd server
python aliyun_qwen_tts.py
```

### 4. 启动NAO客户端

NAO客户端的`main.py`已更新，会自动加载阿里云音频播放器。只需正常启动客户端即可：

```bash
cd naoclient
python main.py
```

## 参数调整

您可以根据需要调整以下参数：

### TTS参数（在`aliyun_tts.py`中）

- **voice**: 音色选择，可选值包括"xiaoyun"、"xiaogang"等
- **speech_rate**: 语速，范围-500到500，0为正常语速
- **pitch_rate**: 音调，范围-500到500，0为正常音调
- **volume**: 音量，范围0到100

### 端口配置

默认使用`NAO_PORT + 2`作为阿里云TTS的通信端口。您可以在以下文件中修改：

- `server/aliyun_tts.py`
- `server/aliyun_qwen_tts.py`
- `naoclient/aliyun_audio_player.py`

## 技术说明

1. **服务器端**：
   - `aliyun_tts.py`: 直接通过HTTP请求调用阿里云TTS API
   - `aliyun_qwen_tts.py`: 整合Qwen模型和阿里云TTS的集成类

2. **NAO客户端**：
   - `aliyun_audio_player.py`: 接收并播放合成的音频文件
   - `main.py`: 已更新以加载阿里云音频播放器

3. **数据流**：
   - 用户语音 → NAO → 服务器 → Qwen生成文本
   - 文本 → 阿里云TTS API → 音频数据 → NAO播放

## 故障排除

1. **未设置阿里云密钥**：确保环境变量已正确设置
2. **NAO无法播放音频**：检查网络连接和端口配置
3. **合成质量问题**：调整TTS参数以获得更好的效果
4. **原有功能异常**：确认是否有端口冲突或资源竞争

## 恢复原有功能

如果需要禁用阿里云TTS功能，只需在`naoclient/main.py`中注释掉相关初始化代码即可。 