/**
 * 随机提示词生成器：面向「每日一图 / 图片网站素材」场景。
 * 多维随机组合（主题/主体/环境/风格/光线/色调/构图/氛围），带最近去重，保证每次不重复。
 */

// 维度池（每项为 { text, en }，en 供英文模型参考）
export interface IdeaDim {
  text: string
  en?: string
}

export const IDEA_POOL: Record<string, IdeaDim[]> = {
  theme: [
    { text: '未来都市', en: 'futuristic city' },
    { text: '深海遗迹', en: 'deep-sea ruins' },
    { text: '云上王国', en: 'kingdom above the clouds' },
    { text: '森林秘境', en: 'hidden forest realm' },
    { text: '蒸汽朋克小镇', en: 'steampunk town' },
    { text: '极光冰川', en: 'aurora glacier' },
    { text: '沙漠绿洲', en: 'desert oasis' },
    { text: '漂浮岛屿', en: 'floating islands' },
    { text: '地下熔岩城', en: 'underground lava city' },
    { text: '星空牧场', en: 'starry pasture' },
    { text: '童话蘑菇村', en: 'fairy-tale mushroom village' },
    { text: '废土公路', en: 'wasteland highway' },
  ],
  subject: [
    { text: '旅行的少女', en: 'traveling girl' },
    { text: '机械兽', en: 'mechanical beast' },
    { text: '独角兽', en: 'unicorn' },
    { text: '发光水母', en: 'glowing jellyfish' },
    { text: '旧式飞艇', en: 'vintage airship' },
    { text: '孤独的灯塔', en: 'lonely lighthouse' },
    { text: '千年古树', en: 'ancient tree' },
    { text: '拾荒机器人', en: 'scavenger robot' },
    { text: '飘落的纸飞机', en: 'falling paper planes' },
    { text: '守望的猫', en: 'watchful cat' },
    { text: '风筝与孩子', en: 'child with a kite' },
    { text: '行吟诗人', en: 'wandering bard' },
  ],
  scene: [
    { text: '晨雾缭绕', en: 'misty morning' },
    { text: '黄昏剪影', en: 'golden dusk silhouette' },
    { text: '午夜霓虹', en: 'midnight neon' },
    { text: '雨后的街角', en: 'rain-soaked street corner' },
    { text: '雪境独行', en: 'snowfield solitude' },
    { text: '花田之间', en: 'among flower fields' },
    { text: '山巅之上', en: 'on the mountain peak' },
    { text: '海底漫步', en: 'undersea walk' },
    { text: '云层之上', en: 'above the clouds' },
    { text: '夜集灯火', en: 'night market lights' },
  ],
  style: [
    { text: '赛博朋克', en: 'cyberpunk' },
    { text: '东方水墨', en: 'chinese ink painting' },
    { text: '浮世绘', en: 'ukiyo-e' },
    { text: '像素艺术', en: 'pixel art' },
    { text: '3D 渲染', en: '3D render' },
    { text: '水彩', en: 'watercolor' },
    { text: '厚涂油画', en: 'impasto oil painting' },
    { text: '黑白摄影', en: 'black-and-white photography' },
    { text: '玻璃拟态', en: 'glassmorphism' },
    { text: '剪纸拼贴', en: 'paper-cut collage' },
    { text: '吉卜力风', en: 'ghibli style' },
    { text: '低多边形', en: 'low poly' },
  ],
  light: [
    { text: '黄金时刻', en: 'golden hour' },
    { text: '霓虹辉光', en: 'neon glow' },
    { text: '月光倾泻', en: 'moonlight' },
    { text: '烛光摇曳', en: 'candlelight' },
    { text: '逆光轮廓', en: 'backlit silhouette' },
    { text: '丁达尔光束', en: 'god rays' },
  ],
  tone: [
    { text: '蓝橙渐变', en: 'blue-orange gradient' },
    { text: '粉紫梦幻', en: 'pastel pink-purple' },
    { text: '冷暖对比', en: 'warm-cold contrast' },
    { text: '低饱和灰调', en: 'low-saturation gray' },
    { text: '青绿生机', en: 'teal-green' },
    { text: '鎏金暖棕', en: 'gilded warm brown' },
  ],
  composition: [
    { text: '特写镜头', en: 'close-up shot' },
    { text: '广角全景', en: 'wide-angle panorama' },
    { text: '居中对称', en: 'centered symmetrical' },
    { text: '三分构图', en: 'rule of thirds' },
    { text: '俯视鸟瞰', en: 'top-down aerial view' },
    { text: '低角度仰拍', en: 'low-angle shot' },
  ],
  mood: [
    { text: '梦幻', en: 'dreamy' },
    { text: '治愈', en: 'healing' },
    { text: '史诗感', en: 'epic' },
    { text: '孤独静谧', en: 'solitary and quiet' },
    { text: '神秘', en: 'mysterious' },
    { text: '热血', en: 'passionate' },
    { text: '浪漫', en: 'romantic' },
    { text: '超现实', en: 'surreal' },
  ],
}

/** 组合为完整中文提示词 */
export function composePrompt(picks: Record<string, IdeaDim | undefined>): string {
  const parts: string[] = []
  if (picks.theme && picks.subject) {
    parts.push(`${picks.theme.text}中的${picks.subject.text}`)
  } else if (picks.theme) {
    parts.push(picks.theme.text)
  } else if (picks.subject) {
    parts.push(picks.subject.text)
  }
  if (picks.scene) parts.push(picks.scene.text)
  if (picks.style) parts.push(`${picks.style.text}风格`)
  if (picks.light) parts.push(picks.light.text)
  if (picks.tone) parts.push(picks.tone.text)
  if (picks.composition) parts.push(picks.composition.text)
  if (picks.mood) parts.push(picks.mood.text)
  const base = parts.join('，')
  return `${base}，高质量、细节丰富、艺术感强`
}

/** 英文回退提示词（供英文模型） */
export function composePromptEn(picks: Record<string, IdeaDim | undefined>): string {
  const parts: string[] = []
  if (picks.theme && picks.subject) {
    parts.push(`${picks.theme?.en ?? picks.theme.text} with ${picks.subject?.en ?? picks.subject.text}`)
  } else if (picks.theme) parts.push(picks.theme.en ?? picks.theme.text)
  else if (picks.subject) parts.push(picks.subject.en ?? picks.subject.text)
  if (picks.scene) parts.push(picks.scene.en ?? picks.scene.text)
  if (picks.style) parts.push(picks.style.en ?? picks.style.text)
  if (picks.light) parts.push(picks.light.en ?? picks.light.text)
  if (picks.tone) parts.push(picks.tone.en ?? picks.tone.text)
  if (picks.composition) parts.push(picks.composition.en ?? picks.composition.text)
  if (picks.mood) parts.push(picks.mood.en ?? picks.mood.text)
  const base = parts.join(', ')
  return `${base}, high quality, highly detailed, artistic`
}

const DIM_KEYS = ['theme', 'subject', 'scene', 'style', 'light', 'tone', 'composition', 'mood'] as const

/** 随机抽取一组维度组合 */
export function randomPicks(): Record<string, IdeaDim> {
  const picks: Record<string, IdeaDim> = {}
  for (const key of DIM_KEYS) {
    const pool = IDEA_POOL[key]
    picks[key] = pool[Math.floor(Math.random() * pool.length)]
  }
  return picks
}

/** 带最近去重的随机提示词（模块内维护最近 8 条，保证每次不重复） */
export function generateRandomPrompt(): { prompt: string; en: string } {
  let prompt = ''
  let en = ''
  for (let attempt = 0; attempt < 20; attempt++) {
    const picks = randomPicks()
    prompt = composePrompt(picks)
    en = composePromptEn(picks)
    if (!recent.some((r) => r === prompt)) break
  }
  recent.push(prompt)
  if (recent.length > 8) recent.shift()
  return { prompt, en }
}

/** 模块级最近记录（会话内去重） */
const recent: string[] = []
