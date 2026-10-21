import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { parseQR } from "../lib/qr.js";
import useQrScanner from "../hooks/useQrScanner.js";

export default function Qr({ acceptQR, toast }) {
  const [text, setText] = useState("");
  const { videoRef, active, starting, reading, camera, scanImage } = useQrScanner({
    acceptQR,
    toast,
  });
  function pasteQR() {
    try {
      acceptQR(parseQR(text));
    } catch (error) {
      toast(error.message);
    }
  }
  return (
    <div className="page">
      <div className="qrarea">
        <div className="qrframe">
          <Icon name="qr" size={76} />
        </div>
        <b style={{ fontSize: 15 }}>Quét QR chuyển khoản</b>
        <p className="note">
          Quét bằng camera hoặc tải ảnh QR để tự điền thông tin chuyển khoản từ mã.
        </p>
        <div className="actions-2" style={{ marginTop: 15 }}>
          <button className="filebutton" disabled={starting || reading} onClick={camera}>
            <Icon name="camera" size={17} /> Mở camera
          </button>
          <label className="filebutton">
            <Icon name="upload" size={17} /> Tải ảnh QR
            <input
              aria-label="Tải ảnh QR"
              type="file"
              accept="image/*"
              hidden
              disabled={reading}
              onChange={(e) => {
                scanImage(e.target.files[0]);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        {reading && (
          <p className="note" role="status">
            Đang đọc ảnh QR...
          </p>
        )}
        <video ref={videoRef} playsInline muted autoPlay className="camera" hidden={!active} />
      </div>
      <div className="section-title" style={{ marginTop: 25 }}>
        Dán nội dung QR
      </div>
      <div className="field">
        <input
          aria-label="Nội dung QR"
          className="input"
          placeholder="VietQR payload / JSON / URL QR"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <button className="cta secondary" onClick={pasteQR}>
        Đọc thông tin QR
      </button>
      <p className="note">
        VietQR thường không chứa tên người nhận; app thật cần tra cứu tên chủ tài khoản qua API ngân
        hàng.
      </p>
    </div>
  );
}
