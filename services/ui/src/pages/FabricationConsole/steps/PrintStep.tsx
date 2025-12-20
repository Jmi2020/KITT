/**
 * PrintStep - Step 4 of fabrication workflow
 *
 * Final step: Send G-code to printer or add to print queue.
 * Shows print time estimate and confirmation before starting.
 */

import { useState } from 'react';
import { StepContainer } from '../../../components/FabricationWorkflow';
import type { SliceResult, PrinterStatus } from '../hooks/useFabricationWorkflow';
import './PrintStep.css';

interface PrintStepProps {
  // State
  sliceResult: SliceResult | null;
  selectedPrinter: string | null;
  printers: PrinterStatus[];
  printJobId: string | null;
  printStatus: string;
  isLoading: boolean;
  isActive: boolean;
  isCompleted: boolean;
  isLocked: boolean;

  // Actions
  onSendToPrinter: (startPrint: boolean) => void;
  onAddToQueue: () => void;
}

export function PrintStep({
  sliceResult,
  selectedPrinter,
  printers,
  printJobId,
  printStatus,
  isLoading,
  isActive,
  isCompleted,
  isLocked,
  onSendToPrinter,
  onAddToQueue,
}: PrintStepProps) {
  const [confirmPrint, setConfirmPrint] = useState(false);

  // Get printer info
  const printer = printers.find((p) => p.printer_id === selectedPrinter);
  const printerName = formatPrinterName(selectedPrinter || '');

  // Get subtitle
  const getSubtitle = () => {
    if (isLocked) return 'Complete slicing to send to printer';
    if (printJobId) return `Print job ${printJobId.slice(0, 8)}... sent to ${printerName}`;
    if (printStatus) return printStatus;
    return `Ready to send to ${printerName}`;
  };

  // Format time
  const formatTime = (seconds?: number): string => {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const handlePrintNow = () => {
    if (!confirmPrint) {
      setConfirmPrint(true);
      return;
    }
    onSendToPrinter(true);
    setConfirmPrint(false);
  };

  const handleCancel = () => {
    setConfirmPrint(false);
  };

  return (
    <StepContainer
      stepNumber={5}
      title="Print"
      subtitle={getSubtitle()}
      isActive={isActive}
      isCompleted={isCompleted}
      isLocked={isLocked}
      isLoading={isLoading}
      collapsible={isCompleted}
      helpText="Send your sliced model to the printer"
    >
      <div className="print-step">
        {/* Print summary */}
        {sliceResult?.status === 'completed' && (
          <div className="print-step__summary">
            <div className="print-step__summary-row">
              <span className="print-step__summary-label">Estimated Time</span>
              <span className="print-step__summary-value">
                {formatTime(sliceResult.estimated_print_time_seconds)}
              </span>
            </div>
            <div className="print-step__summary-row">
              <span className="print-step__summary-label">Filament Usage</span>
              <span className="print-step__summary-value">
                {sliceResult.estimated_filament_grams?.toFixed(1) || '?'}g
              </span>
            </div>
            <div className="print-step__summary-row">
              <span className="print-step__summary-label">Target Printer</span>
              <span className="print-step__summary-value print-step__summary-value--printer">
                {printerName}
                {printer && (
                  <span className={`print-step__printer-status ${printer.is_online ? (printer.is_printing ? 'print-step__printer-status--printing' : 'print-step__printer-status--available') : 'print-step__printer-status--offline'}`}>
                    {printer.is_online
                      ? printer.is_printing
                        ? `Printing ${printer.progress_percent || 0}%`
                        : 'Available'
                      : 'Offline'}
                  </span>
                )}
              </span>
            </div>
          </div>
        )}

        {/* Printer availability warning */}
        {printer && !printer.is_online && (
          <div className="print-step__warning">
            <svg viewBox="0 0 24 24" className="print-step__warning-icon">
              <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span>Printer is offline. G-code will be queued for when it comes online.</span>
          </div>
        )}

        {printer && printer.is_printing && (
          <div className="print-step__info">
            <svg viewBox="0 0 24 24" className="print-step__info-icon">
              <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span>Printer is currently printing. Your job will be queued.</span>
          </div>
        )}

        {/* Confirmation dialog */}
        {confirmPrint && (
          <div className="print-step__confirm">
            <div className="print-step__confirm-header">
              <svg viewBox="0 0 24 24" className="print-step__confirm-icon">
                <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <span>Confirm Print</span>
            </div>
            <p className="print-step__confirm-text">
              Are you sure you want to start printing on <strong>{printerName}</strong>?
              <br />
              Estimated time: <strong>{formatTime(sliceResult?.estimated_print_time_seconds)}</strong>
            </p>
            <div className="print-step__confirm-actions">
              <button
                type="button"
                className="print-step__cancel-btn"
                onClick={handleCancel}
              >
                Cancel
              </button>
              <button
                type="button"
                className="print-step__confirm-btn"
                onClick={handlePrintNow}
                disabled={isLoading}
              >
                {isLoading ? 'Sending...' : 'Start Print'}
              </button>
            </div>
          </div>
        )}

        {/* Action buttons */}
        {!confirmPrint && !printJobId && (
          <div className="print-step__actions">
            <button
              type="button"
              className="print-step__queue-btn"
              onClick={onAddToQueue}
              disabled={isLocked || isLoading || !sliceResult}
            >
              <svg viewBox="0 0 24 24" className="print-step__btn-icon">
                <path d="M4 6h16M4 10h16M4 14h16M4 18h16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Add to Queue
            </button>
            <button
              type="button"
              className="print-step__print-btn"
              onClick={handlePrintNow}
              disabled={isLocked || isLoading || !sliceResult}
            >
              <svg viewBox="0 0 24 24" className="print-step__btn-icon">
                <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" fill="currentColor"/>
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2"/>
              </svg>
              Print Now
            </button>
          </div>
        )}

        {/* Success message */}
        {printJobId && (
          <div className="print-step__success">
            <svg viewBox="0 0 24 24" className="print-step__success-icon">
              <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <div className="print-step__success-content">
              <span className="print-step__success-title">Print Job Sent!</span>
              <span className="print-step__success-detail">
                Job ID: {printJobId.slice(0, 8)}... on {printerName}
              </span>
            </div>
          </div>
        )}
      </div>
    </StepContainer>
  );
}

// Helper function
function formatPrinterName(printerId: string): string {
  const names: Record<string, string> = {
    bambu_h2d: 'Bambu H2D',
    elegoo_giga: 'Elegoo Giga',
    snapmaker_artisan: 'Snapmaker Artisan',
  };
  return names[printerId] || printerId || 'No printer selected';
}

export default PrintStep;
