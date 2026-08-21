/**
 * Original-content provider/BAA router (CONTRACT-phase1 §3.1.4, §4.1 step 3,
 * invariant L11).
 *
 * Provider and production-safety selection examine the ORIGINAL, pre-substitution
 * content and are pinned before any substitution. A PHI-tagged matter (or PHI
 * detected in the original text) routes to a BAA-covered provider; the Anthropic
 * path stays gated by the conjunction `isProductionSafe ∧ CLAUDE_BAA_ENABLED`,
 * which the wrapper enforces on the returned decision.
 *
 * Inspecting substituted (tokenized) text here would defeat L11 — the tokens
 * carry no PHI, so a naive router would wrongly downgrade a PHI matter to a
 * non-BAA provider.
 *
 * N2: the router does NOT expose the original pre-substitution content to any
 * observability callback. The only consumer of the extracted text is the
 * routing decision itself; there is no `onInspect`/log hook that could persist
 * raw content into a trace, error, job, or cache payload.
 *
 * L11: the returned decision PINS the actual provider object selected for the
 * route (BAA vs non-BAA vs forced), so the wrapper invokes the routed provider
 * rather than a fixed adapter.
 */
import type { OriginalContentProviderRouter } from "./protected-ai-provider";

export const DEFAULT_PHI_PATTERNS: readonly RegExp[] = [
  /\bMRN-[A-Za-z0-9]+\b/u, // medical record number
  /\b\d{3}-\d{2}-\d{4}\b/u, // SSN
  /\bDEA-[A-Za-z0-9]+\b/u, // DEA registration
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/u, // email
];

export interface BaaRouterConfig<GenerateOptions, RawProvider> {
  /** Reads the text the router inspects; the wrapper passes the ORIGINAL options. */
  readonly extractOriginalText: (options: GenerateOptions) => string;
  /** The single private raw provider binding (N1); the default when no route-specific
   *  provider is supplied. */
  readonly rawProvider: RawProvider;
  readonly baaProviderId: string;
  readonly nonBaaProviderId: string;
  /** The concrete provider object bound to the BAA route. Defaults to `rawProvider`. */
  readonly baaProvider?: RawProvider;
  /** The concrete provider object bound to the non-BAA route. Defaults to `rawProvider`. */
  readonly nonBaaProvider?: RawProvider;
  /** The concrete provider object bound to the forced route. Defaults to `rawProvider`. */
  readonly forcedProvider?: RawProvider;
  /** When set, forces a specific provider (e.g. the Anthropic path) for its gate. */
  readonly forcedProviderId?: string;
  /** Whether the forced provider itself carries a BAA (Anthropic: false). */
  readonly forcedProviderBaaCovered?: boolean;
  /** CLAUDE_BAA_ENABLED — one half of the conjunctive Anthropic gate. */
  readonly claudeBaaEnabled: boolean;
  /** Production-safety of the forced provider — the other half of the gate. */
  readonly forcedProductionSafe?: boolean;
  readonly matterIsPhiTagged: boolean;
  readonly phiPatterns?: readonly RegExp[];
}

export interface ProviderRoutingDecision<RawProvider> {
  readonly provider: RawProvider;
  readonly isProductionSafe: boolean;
  readonly baaSatisfied: boolean;
  readonly providerId: string;
}

export class OriginalContentBaaRouter<
  GenerateOptions,
  RawProvider,
> implements OriginalContentProviderRouter<GenerateOptions, RawProvider> {
  public constructor(
    private readonly config: BaaRouterConfig<GenerateOptions, RawProvider>,
  ) {}

  public async selectUsingOriginalContent(
    options: GenerateOptions,
  ): Promise<ProviderRoutingDecision<RawProvider>> {
    // L11: the decision is derived from the ORIGINAL content only. The extracted
    // text is used solely to compute the route; it is never handed to an
    // observability callback (N2).
    const originalText = this.config.extractOriginalText(options);

    const patterns = this.config.phiPatterns ?? DEFAULT_PHI_PATTERNS;
    const phiPresent =
      this.config.matterIsPhiTagged ||
      patterns.some((pattern) => {
        pattern.lastIndex = 0;
        return pattern.test(originalText);
      });

    if (this.config.forcedProviderId !== undefined) {
      const baaCovered = this.config.forcedProviderBaaCovered ?? false;
      return {
        // L11: pin the concrete provider bound to the forced route.
        provider: this.config.forcedProvider ?? this.config.rawProvider,
        providerId: this.config.forcedProviderId,
        isProductionSafe: this.config.forcedProductionSafe ?? true,
        // Conjunctive Anthropic gate: BAA is satisfied only when CLAUDE_BAA_ENABLED.
        baaSatisfied: baaCovered ? true : this.config.claudeBaaEnabled,
      };
    }

    if (phiPresent) {
      return {
        // L11: pin the concrete provider bound to the BAA route.
        provider: this.config.baaProvider ?? this.config.rawProvider,
        providerId: this.config.baaProviderId,
        isProductionSafe: true,
        baaSatisfied: true,
      };
    }

    return {
      // L11: pin the concrete provider bound to the non-BAA route.
      provider: this.config.nonBaaProvider ?? this.config.rawProvider,
      providerId: this.config.nonBaaProviderId,
      isProductionSafe: true,
      baaSatisfied: true,
    };
  }
}
