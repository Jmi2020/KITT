import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { Layout } from './Layout';

// Wrapper component for testing
function TestLayout({ initialPath = '/' }: { initialPath?: string }) {
  return (
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<div data-testid="home">Home</div>} />
            <Route path="voice" element={<div data-testid="voice">Voice</div>} />
            <Route path="shell" element={<div data-testid="shell">Shell</div>} />
            <Route path="console" element={<div data-testid="console">Console</div>} />
            <Route path="dashboard" element={<div data-testid="dashboard">Dashboard</div>} />
            <Route path="research" element={<div data-testid="research">Research</div>} />
            <Route path="settings" element={<div data-testid="settings">Settings</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>
  );
}

describe('Layout', () => {
  it('renders the KITTY header', () => {
    render(<TestLayout />);
    // KITTY appears in both the header h1 and the floating badge, so use getAllByText
    const kittyElements = screen.getAllByText('KITTY');
    expect(kittyElements.length).toBeGreaterThanOrEqual(1);
    // Verify the header h1 specifically
    expect(screen.getByRole('heading', { name: 'KITTY' })).toBeInTheDocument();
  });

  it('renders theme toggle button', () => {
    render(<TestLayout />);
    const themeToggle = screen.getByTitle('Toggle theme');
    expect(themeToggle).toBeInTheDocument();
  });

  it('does not show nav items on home page', () => {
    render(<TestLayout initialPath="/" />);
    // On home page, nav items should be hidden
    expect(screen.queryByText(/Voice/)).not.toBeInTheDocument();
  });

  it('shows nav items on non-home pages', () => {
    render(<TestLayout initialPath="/voice" />);
    // On non-home pages, nav items should be visible (use getAllByText for Voice since it matches nav + content)
    expect(screen.getAllByText(/Voice/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Shell/)).toBeInTheDocument();
    expect(screen.getByText(/Fabricate/)).toBeInTheDocument();
    expect(screen.getByText(/Printers/)).toBeInTheDocument();
    expect(screen.getByText(/Research/)).toBeInTheDocument();
    expect(screen.getByText(/Settings/)).toBeInTheDocument();
  });

  it('renders outlet content', () => {
    render(<TestLayout initialPath="/" />);
    expect(screen.getByTestId('home')).toBeInTheDocument();
  });

  it('renders different pages based on route', () => {
    render(<TestLayout initialPath="/dashboard" />);
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();
  });

  it('highlights active nav link', () => {
    render(<TestLayout initialPath="/voice" />);
    const voiceLink = screen.getByRole('link', { name: /Voice/ });
    expect(voiceLink).toHaveClass('active');
  });

  it('renders KittyBadge on non-voice pages', () => {
    render(<TestLayout initialPath="/" />);
    expect(screen.getByTitle('Click to move KITTY')).toBeInTheDocument();
  });

  it('does not render KittyBadge on voice page (voice has its own)', () => {
    render(<TestLayout initialPath="/voice" />);
    // Voice page has its own KittyBadge with special pause behavior, so Layout hides it
    expect(screen.queryByTitle('Click to move KITTY')).not.toBeInTheDocument();
  });
});
