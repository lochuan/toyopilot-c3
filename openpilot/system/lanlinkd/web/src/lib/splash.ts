/** 开机画面：把用户图片画成屏幕所见的 2160×1080 横图再上传。
 *
 * 在浏览器里先画好，写入前看到的预览就是开机时的样子；后端只负责
 * 转成竖屏 BMP 写分区（见 lanlinkd/splash.py）。
 */

export const SPLASH_WIDTH = 2160;
export const SPLASH_HEIGHT = 1080;

/** 等比缩放到刚好装进目标框并居中，其余留黑 */
export function containRect(srcW: number, srcH: number, dstW: number, dstH: number) {
  const scale = Math.min(dstW / srcW, dstH / srcH);
  const width = Math.round(srcW * scale);
  const height = Math.round(srcH * scale);
  return { x: Math.round((dstW - width) / 2), y: Math.round((dstH - height) / 2), width, height };
}

export async function renderSplashJpeg(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const canvas = document.createElement("canvas");
  canvas.width = SPLASH_WIDTH;
  canvas.height = SPLASH_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("浏览器不支持画布");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT);
  const r = containRect(bitmap.width, bitmap.height, SPLASH_WIDTH, SPLASH_HEIGHT);
  ctx.drawImage(bitmap, r.x, r.y, r.width, r.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("图片编码失败"))), "image/jpeg", 0.92),
  );
}
