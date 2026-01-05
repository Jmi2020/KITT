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
            <Route path="interact" element={<div data-testid="interact">Interact</div>} />
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

  it('shows nav items on home page', () => {
    render(<TestLayout initialPath="/" />);
    // Nav items are visible on all pages including home
    expect(screen.getByText(/Interact/)).toBeInTheDocument();
  });

  it('shows nav items on non-home pages', () => {
    render(<TestLayout initialPath="/interact" />);
    // On non-home pages, nav items should be visible (use getAllByText for Interact since it matches nav + content)
    expect(screen.getAllByText(/Interact/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Research/)).toBeInTheDocument();
    expect(screen.getByText(/Fabrication/)).toBeInTheDocument();
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
    render(<TestLayout initialPath="/interact" />);
    const interactLink = screen.getByRole('link', { name: /Interact/ });
    expect(interactLink).toHaveClass('active');
  });

  it('renders KittyBadge on non-interact pages', () => {
    render(<TestLayout initialPath="/" />);
    expect(screen.getByTitle('Click to move KITTY')).toBeInTheDocument();
  });

  it('does not render KittyBadge on interact page (interact has its own)', () => {
    render(<TestLayout initialPath="/interact" />);
    // Interact page has its own KittyBadge with special pause behavior, so Layout hides it
    expect(screen.queryByTitle('Click to move KITTY')).not.toBeInTheDocument();
  });
});
