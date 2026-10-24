/** 下载图片：fetch → blob → a[download]，失败时新窗口打开兜底 */
export async function downloadImage(url: string, name: string) {
  try {
    const res = await fetch(url, { credentials: 'same-origin' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(a.href)
  } catch {
    window.open(url, '_blank')
  }
}

/** 图片实际像素尺寸（加载完成回调） */
export function imgSize(src: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
    img.onerror = () => resolve({ w: 0, h: 0 })
    img.src = src
  })
}
