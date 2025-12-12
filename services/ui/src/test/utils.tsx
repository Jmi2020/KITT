import React, { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { ThemeProvider } from '../contexts/ThemeContext';

// Custom render function that includes providers
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  initialTheme?: 'light' | 'dark';
}

function AllTheProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      {children}
    </ThemeProvider>
  );
}

function customRender(
  ui: ReactElement,
  options?: CustomRenderOptions
) {
  return render(ui, { wrapper: AllTheProviders, ...options });
}

// Re-export everything from testing-library
export * from '@testing-library/react';
export { userEvent } from '@testing-library/user-event';

// Override render with our custom render
export { customRender as render };

// Helper to create mock API responses
export function mockApiResponse<T>(data: T, options: { ok?: boolean; status?: number } = {}) {
  return Promise.resolve({
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  });
}

// Helper to wait for async effects
export async function waitForAsync() {
  await new Promise(resolve => setTimeout(resolve, 0));
}

// Helper to mock fetch for specific URLs
export function mockFetch(responses: Record<string, unknown>) {
  return (url: string) => {
    const response = responses[url];
    if (response) {
      return mockApiResponse(response);
    }
    return mockApiResponse({}, { ok: false, status: 404 });
  };
}
