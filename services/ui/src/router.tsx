import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
  useSearchParams,
} from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import Layout from './components/Layout';

// Lazy load pages for better performance
const Menu = lazy(() => import('./pages/Menu'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const FabricationConsole = lazy(() => import('./pages/FabricationConsole'));
const Projects = lazy(() => import('./pages/Projects'));
const Shell = lazy(() => import('./pages/Shell'));
const WallTerminal = lazy(() => import('./pages/WallTerminal'));
const VisionGallery = lazy(() => import('./pages/VisionGallery'));
const ImageGenerator = lazy(() => import('./pages/ImageGenerator'));
const Research = lazy(() => import('./pages/Research'));
const Results = lazy(() => import('./pages/Results'));
const IOControl = lazy(() => import('./pages/IOControl'));
const MaterialInventory = lazy(() => import('./pages/MaterialInventory'));
const PrintIntelligence = lazy(() => import('./pages/PrintIntelligence'));
const VisionService = lazy(() => import('./pages/VisionService'));
const AutonomyCalendar = lazy(() => import('./pages/AutonomyCalendar'));
const Voice = lazy(() => import('./pages/Voice'));
const Settings = lazy(() => import('./pages/Settings'));

// Loading component for suspense
function PageLoader() {
  return (
    <div className="page-loader">
      <div className="loader-spinner"></div>
      <p>Loading...</p>
    </div>
  );
}

// Wrapper to handle remoteMode prop
import useRemoteMode from './hooks/useRemoteMode';

function DashboardWrapper() {
  const remoteMode = useRemoteMode();
  return <Dashboard remoteMode={remoteMode} />;
}

function WallTerminalWrapper() {
  const remoteMode = useRemoteMode();
  return <WallTerminal remoteMode={remoteMode} />;
}

// Legacy query param redirect handler
// Redirects ?view=<page> to /<page> for backwards compatibility
function LegacyViewRedirect() {
  const [searchParams] = useSearchParams();
  const viewParam = searchParams.get('view');

  const viewToPath: Record<string, string> = {
    menu: '/',
    dashboard: '/dashboard',
    projects: '/projects',
    console: '/console',
    shell: '/shell',
    wall: '/wall',
    vision: '/vision',
    images: '/images',
    research: '/research',
    results: '/results',
    iocontrol: '/iocontrol',
    inventory: '/inventory',
    intelligence: '/intelligence',
    cameras: '/cameras',
    calendar: '/calendar',
    voice: '/voice',
    settings: '/settings',
  };

  useEffect(() => {
    if (viewParam && viewToPath[viewParam]) {
      // Update URL without reloading
      window.history.replaceState(null, '', viewToPath[viewParam]);
    }
  }, [viewParam]);

  if (viewParam && viewToPath[viewParam]) {
    return <Navigate to={viewToPath[viewParam]} replace />;
  }

  // Default to menu if no valid view
  return <Navigate to="/" replace />;
}

// Menu wrapper that passes onNavigate (for backwards compat during transition)
import { useNavigate } from 'react-router-dom';

function MenuWrapper() {
  const navigate = useNavigate();

  const handleNavigate = (view: string) => {
    const viewToPath: Record<string, string> = {
      menu: '/',
      dashboard: '/dashboard',
      projects: '/projects',
      console: '/console',
      shell: '/shell',
      wall: '/wall',
      vision: '/vision',
      images: '/images',
      research: '/research',
      results: '/results',
      iocontrol: '/iocontrol',
      inventory: '/inventory',
      intelligence: '/intelligence',
      cameras: '/cameras',
      calendar: '/calendar',
      voice: '/voice',
      settings: '/settings',
    };

    const path = viewToPath[view] || '/';
    navigate(path);
  };

  return <Menu onNavigate={handleNavigate} />;
}

// Router configuration
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      // Home / Menu
      {
        index: true,
        element: (
          <Suspense fallback={<PageLoader />}>
            <MenuWrapper />
          </Suspense>
        ),
      },

      // Voice & Chat
      {
        path: 'voice',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Voice />
          </Suspense>
        ),
      },
      {
        path: 'shell',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Shell />
          </Suspense>
        ),
      },

      // Fabrication
      {
        path: 'console',
        element: (
          <Suspense fallback={<PageLoader />}>
            <FabricationConsole />
          </Suspense>
        ),
      },
      {
        path: 'projects',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Projects />
          </Suspense>
        ),
      },
      {
        path: 'dashboard',
        element: (
          <Suspense fallback={<PageLoader />}>
            <DashboardWrapper />
          </Suspense>
        ),
      },

      // Media
      {
        path: 'vision',
        element: (
          <Suspense fallback={<PageLoader />}>
            <VisionGallery />
          </Suspense>
        ),
      },
      {
        path: 'images',
        element: (
          <Suspense fallback={<PageLoader />}>
            <ImageGenerator />
          </Suspense>
        ),
      },

      // Research
      {
        path: 'research',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Research />
          </Suspense>
        ),
      },
      {
        path: 'results',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Results />
          </Suspense>
        ),
      },
      {
        path: 'calendar',
        element: (
          <Suspense fallback={<PageLoader />}>
            <AutonomyCalendar />
          </Suspense>
        ),
      },

      // Monitoring
      {
        path: 'cameras',
        element: (
          <Suspense fallback={<PageLoader />}>
            <VisionService />
          </Suspense>
        ),
      },
      {
        path: 'inventory',
        element: (
          <Suspense fallback={<PageLoader />}>
            <MaterialInventory />
          </Suspense>
        ),
      },
      {
        path: 'intelligence',
        element: (
          <Suspense fallback={<PageLoader />}>
            <PrintIntelligence />
          </Suspense>
        ),
      },

      // System
      {
        path: 'iocontrol',
        element: (
          <Suspense fallback={<PageLoader />}>
            <IOControl />
          </Suspense>
        ),
      },
      {
        path: 'settings',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Settings />
          </Suspense>
        ),
      },

      // Special
      {
        path: 'wall',
        element: (
          <Suspense fallback={<PageLoader />}>
            <WallTerminalWrapper />
          </Suspense>
        ),
      },

      // Legacy redirect handler
      {
        path: 'redirect',
        element: <LegacyViewRedirect />,
      },

      // Catch-all redirect to home
      {
        path: '*',
        element: <Navigate to="/" replace />,
      },
    ],
  },
]);

// Router component to be used in App
export function AppRouter() {
  return <RouterProvider router={router} />;
}

export default AppRouter;
