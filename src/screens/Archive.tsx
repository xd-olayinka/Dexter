// Archive (PRD §5.5 / Phase 6) — its own screen now: ingested documents plus notebooks you
// can ask (cited answers) or turn into a two-voice audio briefing. Retrieval is BM25, blended
// with embedding similarity when an embedding model is running (server/archive.py).
import { useBackend } from '../lib/backend'
import { ArchiveCard, DocumentsCard } from './Settings'

export default function Archive() {
  const { online } = useBackend()
  return (
    <div className="content" style={{ maxWidth: 760 }}>
      <h1 className="bigtitle">Archive</h1>
      <p className="subnote lead">
        {online
          ? 'Everything Dexter has read. Group sources into notebooks, ask questions answered only from them — every claim cited — or get a spoken briefing.'
          : 'Your personal intelligence vault. Connect the backend to ingest documents and ask them questions.'}
      </p>
      <DocumentsCard online={online} />
      <ArchiveCard online={online} />
    </div>
  )
}
