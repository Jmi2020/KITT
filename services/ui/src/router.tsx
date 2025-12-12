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
// Dashboard is now consolidated with cameras and materials
const Dashboard = lazy(() => import('./pages/Dashboard'));
const FabricationConsole = lazy(() => import('./pages/FabricationConsole'));
const Projects = lazy(() => import('./pages/Projects'));
const Shell = lazy(() => import('./pages/Shell'));
const WallTerminal = lazy(() => import('./pages/WallTerminal'));
// VisionGallery and ImageGenerator are now part of MediaHub
const MediaHub = lazy(() => import('./pages/MediaHub'));
const ResearchHub = lazy(() => import('./pages/ResearchHub'));
// IOControl is now part of Settings as System tab
// MaterialInventory is now part of Dashboard as Materials tab
// VisionService/cameras is now part of Dashboard as Cameras tab
const PrintIntelligence = lazy(() => import('./pages/PrintIntelligence'));
const Voice = lazy(() => import('./pages/Voice'));
const Settings = lazy(() => import('./pages/Settings/index'));

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
    media: '/media',
    vision: '/media?tab=gallery',
    images: '/media?tab=generate',
    research: '/research',
    results: '/research?tab=results',
    iocontrol: '/settings?tab=system',
    inventory: '/dashboard?tab=materials',
    intelligence: '/intelligence',
    cameras: '/dashboard?tab=cameras',
    calendar: '/research?tab=schedule',
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
      media: '/media',
      vision: '/media?tab=gallery',
      images: '/media?tab=generate',
      research: '/research',
      results: '/research?tab=results',
      iocontrol: '/settings?tab=system',
      inventory: '/dashboard?tab=materials',
      intelligence: '/intelligence',
      cameras: '/dashboard?tab=cameras',
      calendar: '/research?tab=schedule',
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

      // Media Hub (consolidated: VisionGallery + ImageGenerator)
      {
        path: 'media',
        element: (
          <Suspense fallback={<PageLoader />}>
            <MediaHub />
          </Suspense>
        ),
      },
      // Legacy redirects for backwards compatibility
      {
        path: 'vision',
        element: <Navigate to="/media?tab=gallery" replace />,
      },
      {
        path: 'images',
        element: <Navigate to="/media?tab=generate" replace />,
      },

      // Research Hub (consolidated: Research + Results + Calendar)
      {
        path: 'research',
        element: (
          <Suspense fallback={<PageLoader />}>
            <ResearchHub />
          </Suspense>
        ),
      },
      // Legacy redirects for backwards compatibility
      {
        path: 'results',
        element: <Navigate to="/research?tab=results" replace />,
      },
      {
        path: 'calendar',
        element: <Navigate to="/research?tab=schedule" replace />,
      },

      // Monitoring - cameras and inventory are now redirects to Dashboard tabs
      {
        path: 'cameras',
        element: <Navigate to="/dashboard?tab=cameras" replace />,
      },
      {
        path: 'inventory',
        element: <Navigate to="/dashboard?tab=materials" replace />,
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
        path: 'settings',
        element: (
          <Suspense fallback={<PageLoader />}>
            <Settings />
          </Suspense>
        ),
      },
      // Legacy redirect for IOControl -> Settings System tab
      {
        path: 'iocontrol',
        element: <Navigate to="/settings?tab=system" replace />,
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
