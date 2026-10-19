import jsQR from "jsqr";

export function decodeQrPixels({ data, width, height }) {
  return (
    jsQR(new Uint8ClampedArray(data), width, height, {
      inversionAttempts: "attemptBoth",
    })?.data || ""
  );
}

export function readSourceQr(source) {
  const width = source.videoWidth || source.naturalWidth || source.width;
  const height = source.videoHeight || source.naturalHeight || source.height;
  if (!width || !height) return "";
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 2000 / Math.max(width, height));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context)
    throw new Error("Không đọc được dữ liệu ảnh trên trình duyệt này.");
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  return decodeQrPixels(
    context.getImageData(0, 0, canvas.width, canvas.height),
  );
}

export async function decodeQrFile(file) {
  let source;
  let url;
  try {
    if (typeof createImageBitmap === "function") {
      try {
        source = await createImageBitmap(file);
      } catch {
        /* Try the image element decoder. */
      }
    }
    if (!source) {
      url = URL.createObjectURL(file);
      source = await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () =>
          reject(
            new Error("File ảnh không hợp lệ hoặc định dạng chưa được hỗ trợ."),
          );
        img.src = url;
      });
    }
    const payload = readSourceQr(source);
    if (!payload)
      throw new Error(
        "Không tìm thấy mã QR trong ảnh. Hãy chọn ảnh rõ nét, đủ toàn bộ mã QR.",
      );
    return payload;
  } finally {
    source?.close?.();
    if (url) URL.revokeObjectURL(url);
  }
}
