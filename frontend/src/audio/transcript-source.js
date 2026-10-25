// ============ 转写来源决策表（story-7 主路径契约） ============
// 决策规则集中在这一个纯函数里，node:test 钉死：
// 音频一律走后端 provider 链（百炼→火山→vosk），浏览器 SpeechRecognition
// 只做实时预览、绝不作为最终入库文本（PRD pilot-p0-repair story-7）。
// 没有可录音频的环境（SR-only）不伪装：走手动输入，溯源列保持 NULL。

/**
 * 录音路径决策。
 * @param {boolean} speechSupported 浏览器 SpeechRecognition 可用
 * @param {boolean} recorderSupported MediaRecorder + getUserMedia 可用
 * @returns {'dual'|'recorder'|'manual'} 
 *   dual     = SR 实时预览 + MediaRecorder 录音频，停后必上传后端转写
 *   recorder = 只录音不预览（Firefox 等），停后必上传后端转写
 *   manual   = 录不了音频（SR-only 设备或全不支持）——诚实降级：手动文字输入，
 *              会话不带任何 ASR 溯源（0018 列 NULL = 未知）
 */
export function planRecording(speechSupported, recorderSupported) {
  if (recorderSupported && speechSupported) return 'dual';
  if (recorderSupported) return 'recorder';
  if (speechSupported) return 'manual';
  return 'manual';
}
