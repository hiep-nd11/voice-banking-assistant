import { useEffect, useRef, useState } from "react";
import { parseQR } from "../lib/qr.js";
import { decodeQrFile, readSourceQr } from "../lib/qrImage.js";

export default function useQrScanner({ acceptQR, toast }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const frameRef = useRef(null);
  const generation = useRef(0);
  const imageRequest = useRef(0);
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [reading, setReading] = useState(false);

  function stop() {
    generation.current += 1;
    imageRequest.current += 1;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  useEffect(() => stop, []);

  async function camera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      toast("Trình duyệt/cổng HTTP không hỗ trợ camera QR. Hãy dùng HTTPS hoặc localhost.");
      return;
    }
    stop();
    const request = generation.current;
    setActive(false);
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      if (request !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      setActive(true);
      await video.play();
      if (request !== generation.current) return;
      let detector;
      try {
        if (window.BarcodeDetector) detector = new window.BarcodeDetector({ formats: ["qr_code"] });
      } catch {
        /* Use JS decoder. */
      }
      let lastScan = 0;
      const loop = async () => {
        if (request !== generation.current) return;
        if (Date.now() - lastScan < 180) {
          frameRef.current = requestAnimationFrame(loop);
          return;
        }
        lastScan = Date.now();
        try {
          let payload = "";
          if (detector) {
            try {
              payload = (await detector.detect(video))[0]?.rawValue || "";
            } catch {
              detector = null;
            }
          }
          if (!payload) payload = readSourceQr(video);
          if (request !== generation.current) return;
          if (payload) {
            const parsed = parseQR(payload);
            stop();
            setActive(false);
            acceptQR(parsed);
            return;
          }
        } catch {
          /* Continue scanning if a frame cannot be decoded. */
        }
        if (request === generation.current) frameRef.current = requestAnimationFrame(loop);
      };
      frameRef.current = requestAnimationFrame(loop);
    } catch (error) {
      if (request !== generation.current) return;
      stop();
      setActive(false);
      setStarting(false);
      toast("Không mở được camera: " + error.message);
    } finally {
      if (request === generation.current) setStarting(false);
    }
  }

  async function scanImage(file) {
    if (!file) return;
    const request = ++imageRequest.current;
    setReading(true);
    try {
      const payload = await decodeQrFile(file);
      if (request !== imageRequest.current) return;
      const parsed = parseQR(payload);
      stop();
      setActive(false);
      setReading(false);
      acceptQR(parsed);
    } catch (error) {
      if (request === imageRequest.current) toast("Không đọc được QR: " + error.message);
    } finally {
      if (request === imageRequest.current) setReading(false);
    }
  }

  return { videoRef, active, starting, reading, camera, scanImage };
}
