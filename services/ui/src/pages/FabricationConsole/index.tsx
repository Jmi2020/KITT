/**
 * FabricationConsole - Progressive dashboard for 3D printing workflow
 *
 * Workflow: Generate → Orient → Segment → Slice → Print
 *
 * All steps are visible but unlock progressively as prerequisites complete.
 * Integrates with KITTY voice automation for hands-free operation.
 */

import { useMemo } from 'react';
import { WorkflowStepper } from '../../components/FabricationWorkflow';
import { GenerateStep, OrientStep, SegmentStep, SliceStep, PrintStep } from './steps';
import { useFabricationWorkflow, WorkflowStep } from './hooks/useFabricationWorkflow';
import { ModelViewer } from './components';
import ThermalPanel from '../../components/ThermalPanel';
import GcodeConsole from '../../components/GcodeConsole';
import './FabricationConsole.css';

export default function FabricationConsole() {
  const [state, actions, printers] = useFabricationWorkflow();

  // Calculate completed steps for stepper
  const completedSteps = useMemo(() => {
    const completed: WorkflowStep[] = [];
    if (state.selectedArtifact) completed.push(1);
    if (state.orientationSkipped || state.orientedMeshPath) completed.push(2);
    if (state.segmentationSkipped || state.segmentResult || (state.dimensionCheck && !state.dimensionCheck.needs_segmentation)) {
      completed.push(3);
    }
    if (state.sliceResult?.status === 'completed') completed.push(4);
    if (state.printJobId) completed.push(5);
    return completed;
  }, [state.selectedArtifact, state.orientationSkipped, state.orientedMeshPath, state.segmentationSkipped, state.segmentResult, state.dimensionCheck, state.sliceResult, state.printJobId]);

  // Check if step can be navigated to
  const canNavigateTo = (step: WorkflowStep): boolean => {
    switch (step) {
      case 1: return true;
      case 2: return state.selectedArtifact !== null;
      case 3: return state.selectedArtifact !== null &&
        (state.orientationSkipped || state.orientedMeshPath !== null);
      case 4: return state.selectedArtifact !== null &&
        (state.orientationSkipped || state.orientedMeshPath !== null) &&
        (state.segmentationSkipped || !state.segmentationRequired || state.segmentResult !== null);
      case 5: {
        // Standard path: slicing completed
        const sliceReady = state.sliceResult?.status === 'completed' && state.selectedPrinter !== null;
        // Bambu direct path: logged in, Bambu printer, has 3MF
        const isBambuPrinter = state.selectedPrinter?.startsWith('bambu_') || state.selectedPrinter?.includes('bambu');
        const has3mfPath = state.segmentResult?.combined_3mf_path ||
          state.orientedMeshPath ||
          state.selectedArtifact?.metadata?.threemf_location;
        const bambuReady = state.bambuLoggedIn && isBambuPrinter && state.selectedPrinter !== null && !!has3mfPath;
        return sliceReady || bambuReady;
      }
      default: return false;
    }
  };

  // Get selected printer info for Elegoo panel
  const selectedPrinterInfo = printers.find(p => p.printer_id === state.selectedPrinter);

  return (
    <div className="fabrication-console-v2">
      {/* Header */}
      <header className="fabrication-console-v2__header">
        <div className="fabrication-console-v2__title-group">
          <h1 className="fabrication-console-v2__title">Fabrication Console</h1>
          <span className="fabrication-console-v2__subtitle">Generate → Orient & Scale → Segment → Slice → Print</span>
        </div>
        <button
          type="button"
          className="fabrication-console-v2__reset-btn"
          onClick={actions.reset}
        >
          New Session
        </button>
      </header>

      {/* Workflow Stepper */}
      <WorkflowStepper
        currentStep={state.currentStep}
        completedSteps={completedSteps}
        onStepClick={actions.goToStep}
        canNavigateTo={canNavigateTo}
      />

      {/* Main content area with steps and model viewer */}
      <div className="fabrication-console-v2__content">
        {/* Left column: Workflow Steps */}
        <div className="fabrication-console-v2__steps">
          {/* Step 1: Generate */}
          <GenerateStep
            provider={state.provider}
            mode={state.mode}
            inputMode={state.inputMode}
            prompt={state.prompt}
            refineMode={state.refineMode}
            imagePreview={state.imagePreview}
            artifacts={state.artifacts}
            selectedArtifact={state.selectedArtifact}
            isLoading={state.generationLoading}
            error={state.generationError}
            isActive={state.currentStep === 1}
            isCompleted={completedSteps.includes(1)}
            uploadProgress={state.uploadProgress}
            onProviderChange={actions.setProvider}
            onModeChange={actions.setMode}
            onInputModeChange={actions.setInputMode}
            onPromptChange={actions.setPrompt}
            onRefineChange={actions.setRefineMode}
            onImageSelect={actions.setImageFile}
            onClearImage={actions.clearImage}
            onGenerate={actions.generateModel}
            onImport={actions.importModel}
            onSelectArtifact={actions.selectArtifact}
            onSelectFromBrowser={actions.selectArtifactFromBrowser}
          />

          {/* Step 2: Orient and Scale */}
          <OrientStep
            selectedArtifact={state.selectedArtifact}
            orientationAnalysis={state.orientationAnalysis}
            selectedOrientation={state.selectedOrientation}
            orientedMeshPath={state.orientedMeshPath}
            isLoading={state.orientationLoading}
            error={state.orientationError}
            isActive={state.currentStep === 2}
            isCompleted={completedSteps.includes(2)}
            isLocked={!state.selectedArtifact}
            scalingEnabled={state.scalingEnabled}
            targetHeight={state.targetHeight}
            appliedScaleFactor={state.appliedScaleFactor}
            onAnalyze={actions.analyzeOrientation}
            onSelectOrientation={actions.selectOrientation}
            onApplyOrientation={actions.applyOrientation}
            onSkipOrientation={actions.skipOrientation}
            onSetScalingEnabled={actions.setScalingEnabled}
            onSetTargetHeight={actions.setTargetHeight}
          />

          {/* Step 3: Segment */}
          <SegmentStep
            selectedArtifact={state.selectedArtifact}
            orientedMeshPath={state.orientedMeshPath}
            dimensionCheck={state.dimensionCheck}
            segmentationRequired={state.segmentationRequired}
            segmentationSkipped={state.segmentationSkipped}
            segmentResult={state.segmentResult}
            isLoading={state.segmentationLoading}
            error={state.segmentationError}
            isActive={state.currentStep === 3}
            isCompleted={completedSteps.includes(3)}
            isLocked={!canNavigateTo(3)}
            selectedPrinter={state.selectedPrinter || undefined}
            onCheckComplete={() => {
              // The hook handles state updates internally via MeshSegmenter callbacks
            }}
            onSegmentComplete={() => {
              // The hook handles state updates internally via MeshSegmenter callbacks
            }}
            onSkipSegmentation={actions.skipSegmentation}
          />

          {/* Step 4: Slice */}
          <SliceStep
            selectedArtifact={state.selectedArtifact}
            orientedMeshPath={state.orientedMeshPath}
            segmentResult={state.segmentResult}
            selectedPrinter={state.selectedPrinter}
            printerRecommendations={state.printerRecommendations}
            preset={state.preset}
            advancedSettings={state.advancedSettings}
            showAdvanced={state.showAdvanced}
            sliceResult={state.sliceResult}
            isLoading={state.slicingLoading}
            error={state.slicingError}
            isActive={state.currentStep === 4}
            isCompleted={completedSteps.includes(4)}
            isLocked={!canNavigateTo(4)}
            onPrinterSelect={actions.selectPrinter}
            onPresetChange={actions.setPreset}
            onAdvancedSettingsChange={actions.setAdvancedSettings}
            onToggleAdvanced={actions.toggleAdvanced}
            onStartSlicing={actions.startSlicing}
            onSliceComplete={() => {
              // Update state with slice result
            }}
          />

          {/* Step 5: Print */}
          <PrintStep
            sliceResult={state.sliceResult}
            selectedPrinter={state.selectedPrinter}
            printers={printers}
            printJobId={state.printJobId}
            printStatus={state.printStatus}
            isLoading={state.printLoading}
            isActive={state.currentStep === 5}
            isCompleted={completedSteps.includes(5)}
            isLocked={!canNavigateTo(5)}
            bambuLoggedIn={state.bambuLoggedIn}
            input3mfPath={
              state.segmentResult?.combined_3mf_path ||
              state.orientedMeshPath ||
              state.selectedArtifact?.metadata?.threemf_location
            }
            onSendToPrinter={actions.sendToPrinter}
            onAddToQueue={actions.addToQueue}
            onPrintOnBambu={actions.printOnBambu}
          />
        </div>

        {/* Right column: Model Viewer */}
        <aside className="fabrication-console-v2__viewer">
          <ModelViewer
            artifact={state.selectedArtifact}
            isGenerating={state.generationLoading}
          />
        </aside>
      </div>

      {/* Elegoo Control Panel - shown when Elegoo is selected and online */}
      {state.selectedPrinter === 'elegoo_giga' && selectedPrinterInfo?.is_online && (
        <section className="fabrication-console-v2__elegoo-panel">
          <h3 className="fabrication-console-v2__elegoo-title">Elegoo Giga Control</h3>
          <ThermalPanel
            bedTemp={selectedPrinterInfo.bed_temp}
            bedTarget={selectedPrinterInfo.bed_target}
            nozzleTemp={selectedPrinterInfo.extruder_temp}
            nozzleTarget={selectedPrinterInfo.extruder_target}
            bedZones={selectedPrinterInfo.bed_zones}
            onRefresh={actions.fetchPrinters}
          />
          <GcodeConsole printerId="elegoo_giga" />
        </section>
      )}
    </div>
  );
}
