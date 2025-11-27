/**
 * Function Executor
 *
 * Executes KITTY functions based on tool calls from LLM responses.
 * Handles error recovery and result formatting.
 */

import { getFunction, kittyFunctions, type FunctionDefinition } from './kitty-functions';

export interface FunctionCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface FunctionResult {
  success: boolean;
  name: string;
  result?: unknown;
  error?: string;
  duration_ms: number;
}

/**
 * Execute a single function call.
 */
export async function executeFunction(call: FunctionCall): Promise<FunctionResult> {
  const startTime = performance.now();

  const func = getFunction(call.name);
  if (!func) {
    return {
      success: false,
      name: call.name,
      error: `Unknown function: ${call.name}`,
      duration_ms: performance.now() - startTime,
    };
  }

  try {
    const result = await func.handler(call.arguments);
    return {
      success: true,
      name: call.name,
      result,
      duration_ms: performance.now() - startTime,
    };
  } catch (err) {
    return {
      success: false,
      name: call.name,
      error: err instanceof Error ? err.message : String(err),
      duration_ms: performance.now() - startTime,
    };
  }
}

/**
 * Execute multiple function calls in sequence.
 */
export async function executeFunctions(calls: FunctionCall[]): Promise<FunctionResult[]> {
  const results: FunctionResult[] = [];

  for (const call of calls) {
    const result = await executeFunction(call);
    results.push(result);

    // Stop on critical errors (can be customized)
    if (!result.success && isCriticalError(result.error)) {
      break;
    }
  }

  return results;
}

/**
 * Execute multiple function calls in parallel.
 */
export async function executeFunctionsParallel(calls: FunctionCall[]): Promise<FunctionResult[]> {
  return Promise.all(calls.map((call) => executeFunction(call)));
}

/**
 * Parse function calls from LLM response.
 */
export function parseFunctionCalls(response: string): FunctionCall[] {
  const calls: FunctionCall[] = [];

  // Try to parse JSON tool calls
  const jsonMatch = response.match(/```json\s*([\s\S]*?)\s*```/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[1]);
      if (Array.isArray(parsed)) {
        return parsed.filter((item) => item.name && item.arguments);
      }
      if (parsed.name && parsed.arguments) {
        return [parsed];
      }
    } catch {
      // Continue to other parsing methods
    }
  }

  // Try to parse function_call format
  const functionCallMatch = response.match(/<function_call>\s*([\s\S]*?)\s*<\/function_call>/);
  if (functionCallMatch) {
    try {
      const parsed = JSON.parse(functionCallMatch[1]);
      if (parsed.name && parsed.arguments) {
        return [parsed];
      }
    } catch {
      // Continue
    }
  }

  // Try to extract from tool_use format
  const toolUseMatches = response.matchAll(/<tool_use>\s*([\s\S]*?)\s*<\/tool_use>/g);
  for (const match of toolUseMatches) {
    try {
      const parsed = JSON.parse(match[1]);
      if (parsed.name && parsed.arguments) {
        calls.push(parsed);
      }
    } catch {
      // Skip malformed
    }
  }

  return calls;
}

/**
 * Format function results for display.
 */
export function formatFunctionResults(results: FunctionResult[]): string {
  if (results.length === 0) {
    return 'No functions executed.';
  }

  return results
    .map((r) => {
      const status = r.success ? '✓' : '✗';
      const timing = `(${r.duration_ms.toFixed(0)}ms)`;

      if (r.success) {
        const resultStr =
          typeof r.result === 'object' ? JSON.stringify(r.result, null, 2) : String(r.result);
        return `${status} ${r.name} ${timing}\n${resultStr}`;
      } else {
        return `${status} ${r.name} ${timing}\nError: ${r.error}`;
      }
    })
    .join('\n\n');
}

/**
 * Check if an error is critical (should stop execution).
 */
function isCriticalError(error?: string): boolean {
  if (!error) return false;

  const criticalPatterns = [
    /authorization/i,
    /authentication/i,
    /permission denied/i,
    /not authorized/i,
    /rate limit/i,
  ];

  return criticalPatterns.some((pattern) => pattern.test(error));
}

/**
 * Get available function names.
 */
export function getAvailableFunctions(): string[] {
  return kittyFunctions.map((f) => f.name);
}

/**
 * Validate function arguments against schema.
 */
export function validateFunctionArgs(
  name: string,
  args: Record<string, unknown>
): { valid: boolean; errors: string[] } {
  const func = getFunction(name);
  if (!func) {
    return { valid: false, errors: [`Unknown function: ${name}`] };
  }

  const errors: string[] = [];
  const { properties, required = [] } = func.parameters;

  // Check required fields
  for (const field of required) {
    if (!(field in args) || args[field] === undefined || args[field] === null) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  // Check field types
  for (const [key, value] of Object.entries(args)) {
    const propDef = properties[key];
    if (!propDef) {
      // Unknown field, warn but allow
      continue;
    }

    // Check enum values
    if (propDef.enum && !propDef.enum.includes(value as string)) {
      errors.push(`Invalid value for ${key}: ${value}. Must be one of: ${propDef.enum.join(', ')}`);
    }

    // Basic type checking
    if (propDef.type === 'string' && typeof value !== 'string') {
      errors.push(`Field ${key} must be a string`);
    }
  }

  return { valid: errors.length === 0, errors };
}
