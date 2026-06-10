import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { BetLeg } from "../api/types";

type BetSlipContextValue = {
  legs: BetLeg[];
  addLeg: (leg: BetLeg) => void;
  removeLeg: (index: number) => void;
  clear: () => void;
};

const BetSlipContext = createContext<BetSlipContextValue | null>(null);

export function BetSlipProvider({ children }: { children: React.ReactNode }) {
  const [legs, setLegs] = useState<BetLeg[]>([]);

  const addLeg = useCallback((leg: BetLeg) => {
    setLegs((current) => {
      const filtered = current.filter(
        (item) => !(item.match_id === leg.match_id && item.play_type === leg.play_type),
      );
      return [...filtered, leg].slice(0, 8);
    });
  }, []);

  const removeLeg = useCallback((index: number) => {
    setLegs((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }, []);

  const clear = useCallback(() => setLegs([]), []);

  const value = useMemo(() => ({ legs, addLeg, removeLeg, clear }), [addLeg, clear, legs, removeLeg]);
  return <BetSlipContext.Provider value={value}>{children}</BetSlipContext.Provider>;
}

export function useBetSlip() {
  const value = useContext(BetSlipContext);
  if (!value) {
    throw new Error("useBetSlip must be used inside BetSlipProvider");
  }
  return value;
}
