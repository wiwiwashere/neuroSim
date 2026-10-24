import { AgentPanel } from "@/components/workspace/agent-panel";
import { DiseasePicker, GenePicker } from "@/components/workspace/gene-picker";
import { MappingChain } from "@/components/workspace/mapping-chain";
import { Perturbation } from "@/components/workspace/perturbation";
import { Results } from "@/components/workspace/results";
import { TopBar } from "@/components/workspace/top-bar";

// One workspace page: inputs on the left, results in the centre, the agent on
// the right. See frontend/SCREENS.md.
export default function Workspace() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid min-h-0 grid-cols-[340px_minmax(0,1fr)_360px]">
        <aside className="min-h-0 space-y-6 overflow-y-auto border-r px-4 py-5">
          <DiseasePicker />
          <GenePicker />
          <MappingChain />
          <Perturbation />
        </aside>
        <main className="min-h-0">
          <Results />
        </main>
        <AgentPanel />
      </div>
    </div>
  );
}
