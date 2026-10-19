import Icon from "../components/Icon.jsx";
import Services from "../components/Services.jsx";

export default function More({ service }) {
  return (
    <div className="page">
      <div className="section-title">Tài chính mỗi ngày</div>
      <Services service={service} />
      <div className="insight" style={{ marginTop: 38 }}>
        <div>
          <Icon name="shield" size={25} />
        </div>
        <div>
          <b style={{ fontSize: 12 }}>Môi trường mô phỏng</b>
          <p>
            Không kết nối Core Banking, không phát sinh giao dịch tiền thật.
          </p>
        </div>
      </div>
    </div>
  );
}
