/**
 * WorkflowStepper - Visual indicator for the 5-step fabrication workflow
 *
 * Displays: [1] GENERATE → [2] ORIENT → [3] SEGMENT → [4] SLICE → [5] PRINT
 * Shows current step, completed steps, and locked future steps
 */

import { WorkflowStep } from '../../pages/FabricationConsole/hooks/useFabricationWorkflow';
import './WorkflowStepper.css';

interface StepConfig {
  number: WorkflowStep;
  label: string;
  shortLabel: string;
}

const STEPS: StepConfig[] = [
  { number: 1, label: 'Generate', shortLabel: 'GEN' },
  { number: 2, label: 'Orient & Scale', shortLabel: 'ORI' },
  { number: 3, label: 'Segment', shortLabel: 'SEG' },
  { number: 4, label: 'Slice', shortLabel: 'SLC' },
  { number: 5, label: 'Print', shortLabel: 'PRT' },
];

interface WorkflowStepperProps {
  currentStep: WorkflowStep;
  completedSteps: WorkflowStep[];
  onStepClick?: (step: WorkflowStep) => void;
  canNavigateTo?: (step: WorkflowStep) => boolean;
}

export function WorkflowStepper({
  currentStep,
  completedSteps,
  onStepClick,
  canNavigateTo,
}: WorkflowStepperProps) {
  const getStepStatus = (step: WorkflowStep): 'active' | 'completed' | 'pending' | 'locked' => {
    if (step === currentStep) return 'active';
    if (completedSteps.includes(step)) return 'completed';
    if (canNavigateTo?.(step)) return 'pending';
    return 'locked';
  };

  const handleClick = (step: WorkflowStep) => {
    if (canNavigateTo?.(step) && onStepClick) {
      onStepClick(step);
    }
  };

  return (
    <div className="workflow-stepper" role="navigation" aria-label="Fabrication workflow steps">
      {STEPS.map((step, index) => {
        const status = getStepStatus(step.number);
        const isClickable = canNavigateTo?.(step.number) && onStepClick;

        return (
          <div key={step.number} className="workflow-stepper__step-wrapper">
            <button
              className={`workflow-stepper__step workflow-stepper__step--${status}`}
              onClick={() => handleClick(step.number)}
              disabled={status === 'locked'}
              aria-current={status === 'active' ? 'step' : undefined}
              aria-label={`Step ${step.number}: ${step.label}${status === 'completed' ? ' (completed)' : status === 'locked' ? ' (locked)' : ''}`}
              type="button"
              tabIndex={isClickable ? 0 : -1}
            >
              <span className="workflow-stepper__number">
                {status === 'completed' ? (
                  <svg viewBox="0 0 16 16" className="workflow-stepper__check" aria-hidden="true">
                    <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 111.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
                  </svg>
                ) : (
                  step.number
                )}
              </span>
              <span className="workflow-stepper__label">{step.label}</span>
              <span className="workflow-stepper__short-label">{step.shortLabel}</span>
            </button>

            {index < STEPS.length - 1 && (
              <div
                className={`workflow-stepper__connector ${
                  completedSteps.includes(step.number) ? 'workflow-stepper__connector--completed' : ''
                }`}
                aria-hidden="true"
              >
                <svg viewBox="0 0 24 8" preserveAspectRatio="none">
                  <path d="M0 4 L20 4 L16 0 M20 4 L16 8" fill="none" strokeWidth="1.5" />
                </svg>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default WorkflowStepper;
