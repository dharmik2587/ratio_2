import { useEffect, useState } from 'react'
import { Header } from './components/ui'
import AnalysisPage from './pages/AnalysisPage'
import BenchmarksPage from './pages/BenchmarksPage'
import GovernancePage from './pages/GovernancePage'
import DemoPage from './pages/DemoPage'
import { getHealth } from './api'

export default function App() {
  const [page, setPage] = useState('analysis')
  const [mission, setMission] = useState('ROUTE_PLANNING')
  const [offline, setOffline] = useState(false)
  useEffect(() => {
    getHealth()
      .then(h => setOffline(h.claude_mode !== 'CLAUDE_EXPLANATION_ENABLED'))
      .catch(() => setOffline(true))
  }, [])
  return <>
    <Header page={page} onPage={setPage} offline={offline} />
    {page === 'analysis' && <AnalysisPage mission={mission} onMission={setMission} offline={offline} />}
    {page === 'benchmarks' && <BenchmarksPage />}
    {page === 'governance' && <GovernancePage />}
    {page === 'demo' && <DemoPage offline={offline} />}
  </>
}
