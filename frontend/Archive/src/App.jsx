import { useState } from 'react'
import Chat from './Chat.jsx'
import Sidebar from './Sidebar.jsx'

export default function App() {
  const [exampleQuery, setExampleQuery] = useState(null)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '220px minmax(0, 1fr)',
        height: '100vh',
        overflow: 'hidden',
      }}
    >
      <Sidebar onSelectExample={setExampleQuery} />
      <Chat
        exampleQuery={exampleQuery}
        onExampleConsumed={() => setExampleQuery(null)}
      />
    </div>
  )
}
