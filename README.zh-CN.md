# OpenTryOn · 开源 AI 试衣工具箱

[English documentation](README.md)

上传人物图与服装图，选择上装 / 下装 / 连衣裙 / 外套，生成试衣图，通过滑块对比前后效果，并下载 PNG。包含响应式 Web 工作台、异步 API、任务队列、图片保留期限、Docker 配置，以及可替换的模型接口。

**当前验证范围：** Web 与 API 流程已有自动测试；FASHN 官方在线服务已返回一次真实上装试衣样图。本地模型推理及额外分割合成效果尚未在开发机（RTX 3050、4GB 显存）验证；Docker 环境亦未在该机器运行验证。没有以静态图片冒充生成结果的后端。

## 本地启动

在本项目目录运行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://localhost:8000；API 文档位于 http://localhost:8000/docs。

## 改成你自己的品牌

无需修改应用代码，在 `.env` 中设置：

```dotenv
VTON_APP_NAME=你的品牌名
VTON_APP_TAGLINE=你的品牌标语
VTON_REPOSITORY_URL=https://github.com/你的账号/你的仓库
```

网页标题、Logo 首字母、页脚、关于弹窗、API 标题、项目源码入口和下载文件名都会自动更新。重新发布时必须保留 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 及其中列出的上游许可；验证素材、网页示例和推理依赖仍遵循各自记录的许可。发布替换图片前，请确认拥有再分发权和肖像使用权。

确定 GitHub 账号和仓库名后，可执行：

```powershell
git add .
git commit -m "Initial open-source release"
gh repo create 你的仓库名 --public --source=. --remote=origin --push
```

`.env`、生成图片、模型权重、缓存和本地日志已加入 `.gitignore`，不会进入仓库。

首次可以浏览工作台、上传图片和载入示例，但没有配置模型时生成按钮会禁用。页面中的示例拼贴是两张输入照片，不是试衣结果。

## 配置推理

### 无 GPU：官方在线演示

在 `.env` 中设置 `VTON_PROVIDER=space` 并重启，即可使用 FASHN 官方 Hugging Face 演示服务，无需下载模型。当前开发机已采用此配置；仓库模板仍默认使用本地后端。

载入示例或上传图片后，需要**主动勾选同意发送到公开服务**才能生成。图片会发送到 FASHN 的 Hugging Face Space，远端副本保留期限由服务运营者控制；删除本机会话不会删除远端副本。服务有公共额度和排队限制，适合试用，不保证持续可用。

此模式使用模型原生的人物/姿态保持能力，**没有本地后端额外的分割合成像素保护**，因此保护开关会禁用。API 请求须提供 `allow_public_upload=true` 与 `preserve=false`，缺少明确同意会被拒绝。

仅用项目公开示例执行真实推理验证：

```powershell
.\.venv\Scripts\python scripts/smoke_public_demo.py
```

结果及任务记录保存到 `test-results/`。这个脚本不会在 CI 自动运行，避免消耗公共服务额度。

### 本地 GPU

请先安装匹配显卡驱动的 PyTorch / CUDA 版本，再运行：

```powershell
.\.venv\Scripts\python -m pip install -e ".[inference]"
.\.venv\Scripts\python scripts/download_weights.py
```

重启应用。模型约 2GB，另有姿态检测与人体分割权重。预留数 GB 磁盘空间。4GB 显存不是本项目已支持、已验证的运行目标；建议准备更大显存的 GPU，并先做真实样图验证。CPU 可运行但速度很慢，配置方式参见英文 README。

### 远程 GPU

在 GPU 服务器部署同一套工具箱，使用本地模型并设置 `VTON_API_KEY`。在本机 `.env` 中设置：

```dotenv
VTON_PROVIDER=remote
VTON_REMOTE_URL=https://你的GPU服务器
VTON_REMOTE_API_KEY=服务器的密钥
```

重启本机应用。这里连接的是本工具箱的 API，不是 FASHN 商业 API。密钥留在服务端；本机网页访问密钥可单独配置。

## Docker

```bash
docker compose up --build -d
```

默认构建轻量 Web 镜像，可连接远程 GPU。若使用本地 NVIDIA GPU，先准备权重与 NVIDIA Container Toolkit，再运行：

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
```

详尽权重下载、Docker 卷权限、CPU 配置、接口调用示例、环境变量、扩展模型方法，见 [README.md](README.md)。

## 保持人物与背景的方式

首个适配器使用 FASHN VTON 1.5 的姿态条件生成。默认开启额外的分割合成保护：把衣物编辑范围外的原图像素保留下来，并锁定识别到的人脸、头发、帽子、眼镜等区域。输出尺寸与输入人物图一致。

这是尽力保护机制，不是百分之百保真保证。分割误差、交叉手臂、宽松衣物和复杂姿态可能产生瑕疵。外套映射为上半身换装，不代表完整的多层穿搭功能。模型原生分辨率为 576×864，恢复原图尺寸不等同于恢复原生高分辨率衣料细节。

## 开源与许可

工具箱原创代码采用 MIT。已调研 FASHN VTON、CatVTON、IDM-VTON，选择了接口清晰、易于接入的 FASHN 作为首个适配器。

FASHN 主代码和模型权重声明 Apache-2.0，但其 human parser 继承 NVIDIA SegFormer 的非商业研究/评估使用限制，因此**不能把默认推理栈整体视为无限制商用**。关闭界面中的保护开关也不会移除上游内部的 parser 依赖。细节和来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

代码、许可证、CI、贡献指南、安全政策与 GitHub 模板均已准备好，可作为新仓库发布。

## 测试

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check app tests scripts
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python scripts/browser_check.py
```

浏览器测试使用仅存在于测试目录的确定性图片处理器，验证交互与 API 链路，不评估 AI 试衣效果。生成的截图位于被 Git 忽略的 `test-results/`。
