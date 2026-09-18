'use strict';

// Localize presentation only. API categories, job states and configuration keys stay stable.
function categoryName(value) {
  return { top: '上装', bottom: '下装', dress: '连衣裙', outerwear: '外套' }[value] || '服装';
}

function statusName(value) {
  return { queued: '排队中', running: '生成中', completed: '已完成', failed: '生成失败' }[value] || '未知状态';
}

function providerName(provider) {
  if (provider.mode === 'public') return 'FASHN · 官方在线演示';
  if (provider.mode === 'remote') return '远程 GPU 服务';
  return provider.name === 'Test fixture (not AI)' ? '测试服务（非 AI）' : provider.name;
}

const serviceMessages = {
  'Model installed · loads on first generation': '模型已安装，将在首次生成时加载。',
  'Install the inference extra and download model weights. See Setup.': '请先安装推理依赖并下载模型权重，操作方法见“模型与设置”。',
  'Remote worker configured; connection checked on generation': '远程推理服务已配置，将在生成时检查连接。',
  'Set VTON_REMOTE_URL to your GPU worker URL.': '请将 VTON_REMOTE_URL 设置为你的 GPU 推理服务地址。',
  'Official Hugging Face demo. Images leave your device after explicit consent. Public quotas and availability apply; extra pixel-lock protection is unavailable.': '当前使用官方 Hugging Face 在线演示。只有明确同意后才会上传图片；受公共额度与服务可用性限制，不支持额外的像素保护。',
  'Server restarted during generation. Please try again.': '生成过程中服务重启，请重新提交试衣任务。',
  'The generation queue is full. Please try again shortly.': '当前生成队列已满，请稍后重试。',
  'GPU memory exhausted. Use a GPU with more memory or a remote worker.': '显存不足，请使用显存更大的 GPU 或连接远程推理服务。',
  'Wait for generation to finish before deleting this session.': '任务仍在生成中，请等待完成后再删除。',
  'Invalid session path.': '试衣记录路径无效。',
  'Each image must be between 1 byte and 15 MB.': '图片不能为空，每张图片不得超过 15 MB。',
  'Use a JPEG, PNG, or WebP image.': '请使用 JPEG、PNG 或 WebP 格式的图片。',
  'Images must be at least 128 × 128 and no more than 24 megapixels.': '图片至少为 128 × 128 像素，且总像素不超过 2400 万。',
  'This file is not a valid, supported image.': '无法识别这张图片，请选择有效的 JPG、PNG 或 WebP 文件。',
  'No editable garment region was detected. Try a clear, front-facing model photo.': '未检测到可换装区域，请换一张清晰、正面的人物照片。',
  'Upload too large. Maximum 15 MB per image.': '上传文件过大，每张图片最大为 15 MB。',
  'A valid X-API-Key header is required.': '需要有效的 API 密钥，请点击右上角 T 按钮配置连接。',
  'Explicit consent is required: set allow_public_upload=true.': '请先勾选同意将图片发送到公开演示服务。',
  'The public demo has no extra pixel-lock protection. Set preserve=false.': '在线演示不支持额外的像素保护，请关闭此选项。',
  'Session not found or expired.': '试衣记录不存在或已过期。',
  'The result is not ready yet.': '结果尚未生成，请稍候。',
  'Image no longer available.': '图片已被清理或无法访问。',
  'Please explicitly allow sending these images to the public demo.': '请明确同意将这些图片发送到公开演示服务。',
  'The public demo supports model-guided preservation only. Set preserve=false.': '在线演示仅支持模型自身的人物保持能力，请关闭额外的像素保护。',
  'Public demo returned an incompatible upload response.': '在线服务返回了无法识别的上传响应，请稍后重试。',
  'Public demo returned an invalid job identifier.': '在线服务返回的任务编号无效，请稍后重试。',
  'The public demo timed out. Please try again later.': '在线生成超时，请稍后重试。',
  'The public demo is unavailable or its GPU quota is exhausted. Try again later or use your own GPU worker.': '在线演示暂时不可用，或 GPU 额度已用完。请稍后重试，也可使用自己的 GPU 服务。',
  'Public demo did not return a valid image file.': '在线服务未返回有效图片，请重新生成。',
  'Public demo returned an unexpectedly large result.': '在线服务返回的图片过大，无法接收。',
  'Could not reach the official public demo. Check your connection or try again later.': '无法连接官方在线演示，请检查网络或稍后重试。',
  'Failed to fetch': '网络连接失败，请检查网络与本地服务是否正在运行。',
  'NetworkError when attempting to fetch resource.': '网络连接失败，请检查网络与本地服务是否正在运行。',
  'Load failed': '加载失败，请检查网络连接。',
  'Test-only provider': '仅用于验证交互流程的测试服务。',
};

function zhMessage(message) {
  if (!message) return '';
  if (serviceMessages[message]) return serviceMessages[message];
  const incident = message.match(/Generation failed.*reference ([a-f0-9]+)\)/);
  if (incident) return `生成失败，请检查模型配置及服务日志（错误编号：${incident[1]}）。`;
  if (/timeout|timed out|aborted/i.test(message)) return '请求超时或已中断，请稍后重试。';
  if (/[\u3400-\u9fff]/.test(message)) return message;
  return '操作未能完成，请稍后重试；如持续出现，请检查服务配置和日志。';
}
