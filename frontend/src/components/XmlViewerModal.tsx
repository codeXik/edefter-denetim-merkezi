interface XmlViewerSource {
  key: string;
  label: string;
  path: string;
  count?: number;
}

interface XmlViewerModalProps {
  title: string;
  subtitle: string;
  visible: boolean;
  sources: XmlViewerSource[];
  selectedKey: string | null;
  xmlContent: string;
  xmlFileName: string;
  truncated: boolean;
  loading: boolean;
  onClose: () => void;
  onSelectSource: (key: string) => void;
}

export function XmlViewerModal({
  title,
  subtitle,
  visible,
  sources,
  selectedKey,
  xmlFileName,
  truncated,
  loading,
  onClose,
  onSelectSource,
}: XmlViewerModalProps) {
  const selectedSource = sources.find((source) => source.key === selectedKey) ?? sources[0] ?? null;
  const documentSrc = selectedSource ? toFileUri(selectedSource.path) : "";

  if (!visible) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card xml-modal-card xml-modal-card-wide" onClick={(event) => event.stopPropagation()}>
        <div className="card-header-row">
          <div>
            <h2 className="section-title">{title}</h2>
            <p className="section-subtitle">{subtitle}</p>
          </div>
          <button className="button button-secondary" onClick={onClose} type="button">Kapat</button>
        </div>

        <div className="xml-source-row">
          {sources.map((source) => (
            <button
              key={source.key}
              className={`button ${selectedKey === source.key ? "button-primary" : "button-secondary"}`}
              onClick={() => onSelectSource(source.key)}
              type="button"
            >
              {source.label}{source.count && source.count > 1 ? ` (${source.count})` : ""}
            </button>
          ))}
        </div>

        <div className="xml-viewer-meta">
          <span>{xmlFileName || "XML seçilmedi"}</span>
          {truncated ? <span>Büyük dosya olduğu için kısaltılmış önizleme gösteriliyor.</span> : null}
        </div>

        <div className="xml-viewer-shell xml-viewer-shell-document">
          {loading ? (
            <div className="compact-empty-state">XML yükleniyor...</div>
          ) : documentSrc ? (
            <iframe className="xml-document-frame" src={documentSrc} title={xmlFileName || "XML belge görünümü"} />
          ) : (
            <div className="compact-empty-state">Belge görünümü hazırlanamadı.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function toFileUri(path: string) {
  const normalized = path.replace(/\\/g, "/");
  return `file:///${encodeURI(normalized)}`;
}
