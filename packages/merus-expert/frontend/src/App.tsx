// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { AppShell } from './components/layout'
import { useRouter } from './router'
import { DashboardPage } from './components/pages/Dashboard'
import { AIAssistantPage } from './components/pages/AIAssistant'
import { CasesPage, CaseDetail } from './components/pages/Cases'
import { NewMatterPage } from './components/pages/NewMatter'
import { BillingPage } from './components/pages/Billing'
import { ActivitiesPage } from './components/pages/Activities'
import { SettingsPage } from './components/pages/Settings'

function AppRouter() {
  const { currentRoute, params } = useRouter()

  switch (currentRoute) {
    case '/dashboard':
      return <DashboardPage />
    case '/ai':
      return <AIAssistantPage />
    case '/cases':
      return <CasesPage />
    case '/cases/:id':
      return <CaseDetail caseId={params.id} />
    case '/new-matter':
      return <NewMatterPage />
    case '/billing':
      return <BillingPage />
    case '/activities':
      return <ActivitiesPage />
    case '/settings':
      return <SettingsPage />
    default:
      return <DashboardPage />
  }
}

function App() {
  return (
    <AppShell>
      <AppRouter />
    </AppShell>
  )
}

export default App
