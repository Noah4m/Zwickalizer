const s = {
  panel: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(180deg, #12151a 0%, #0e1115 100%)',
    borderLeft: '1px solid var(--border)',
    minWidth: 0,
  },
  header: {
    padding: '18px 22px 16px',
    borderBottom: '1px solid var(--border)',
    background: 'rgba(18, 21, 26, 0.88)',
    backdropFilter: 'blur(10px)',
  },
  eyebrow: {
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    color: 'var(--accent3)',
    marginBottom: '4px',
  },
  title: {
    fontSize: '20px',
    fontWeight: 500,
    color: '#eef2f7',
  },
  subtitle: {
    marginTop: '6px',
    fontSize: '12px',
    color: 'var(--text2)',
    fontFamily: 'var(--font-mono)',
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '22px',
  },
  empty: {
    height: '100%',
    border: '1px dashed var(--border2)',
    borderRadius: '18px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '24px',
    color: 'var(--text3)',
    background: 'radial-gradient(circle at top, rgba(96, 165, 250, 0.08), transparent 42%)',
  },
  emptyBig: {
    fontFamily: 'var(--font-mono)',
    fontSize: '22px',
    color: 'var(--border2)',
    marginBottom: '10px',
  },
  plotCard: {
    background: '#0b0e12',
    border: '1px solid var(--border)',
    borderRadius: '20px',
    padding: '14px',
    boxShadow: '0 24px 48px rgba(0, 0, 0, 0.28)',
  },
  image: {
    display: 'block',
    width: '100%',
    height: 'auto',
    borderRadius: '14px',
    background: '#111318',
  },
  metaRow: {
    display: 'flex',
    gap: '10px',
    flexWrap: 'wrap',
    marginTop: '14px',
  },
  chip: {
    padding: '6px 10px',
    borderRadius: '999px',
    background: 'rgba(96, 165, 250, 0.12)',
    border: '1px solid rgba(96, 165, 250, 0.18)',
    color: '#bdd8ff',
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
  },
}

export default function PlotPanel({ plot }) {
  return (
    <aside style={s.panel}>
      <div style={s.header}>
        <div style={s.eyebrow}>Visualization</div>
        <div style={s.title}>{plot?.title || 'Plot output'}</div>
        <div style={s.subtitle}>
          {plot ? `${plot.plot_type} chart · ${plot.series_name}` : 'Generated plots appear here directly from the plot tool'}
        </div>
      </div>

      <div style={s.content}>
        {!plot ? (
          <div style={s.empty}>
            <div>
              <div style={s.emptyBig}>PLOT//PANEL</div>
              Ask for a visualisation and the generated image will appear here.
            </div>
          </div>
        ) : (
          <div style={s.plotCard}>
            <img src={plot.image_data_url} alt={plot.title} style={s.image} />
            <div style={s.metaRow}>
              <div style={s.chip}>{plot.series_name}</div>
              <div style={s.chip}>{plot.summary.point_count} points</div>
              <div style={s.chip}>min {plot.summary.min_value}</div>
              <div style={s.chip}>max {plot.summary.max_value}</div>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
