import { AgentPanel } from "@/components/workspace/agent-panel";
import { DirectTargets } from "@/components/workspace/direct-targets";
import { DiseasePicker, GenePicker } from "@/components/workspace/gene-picker";
import { MappingChain } from "@/components/workspace/mapping-chain";
import { PaperEvidence } from "@/components/workspace/paper-evidence";
import { Perturbation } from "@/components/workspace/perturbation";
import { Results } from "@/components/workspace/results";
import { TopBar } from "@/components/workspace/top-bar";

// One workspace page: inputs on the left, results in the centre, the agent on
// the right. See frontend/SCREENS.md.
export default function Workspace() {
  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr] xl:h-screen xl:overflow-hidden">
      <TopBar />
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[340px_minmax(0,1fr)_360px]">
        <aside className="min-h-0 space-y-6 border-b px-4 py-5 lg:overflow-y-auto lg:border-r lg:border-b-0">
          <DiseasePicker />
          <GenePicker />
          <MappingChain />
          <DirectTargets />
          <PaperEvidence />
          <Perturbation />
        </aside>
        <main className="min-h-[70vh] lg:min-h-0">
          <Results />
        </main>
        <AgentPanel />
      </div>
    </div>
  );
}
