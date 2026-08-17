/* eslint-disable react-hooks/refs -- see the note below */

// `refs.setReference` and `refs.setFloating` are Floating UI's public API, and both
// are callback ref *setters* rather than reads of a `.current` value. The rule is
// right in general — reading a ref during render hides updates — but it cannot tell
// a setter from a read when the object is named `refs`. Disabled for this file only,
// not globally.
import {
  FloatingArrow,
  FloatingPortal,
  arrow,
  flip,
  offset,
  shift,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  useRole,
  useTransitionStyles,
} from "@floating-ui/react";
import { useState } from "react";
import type { ReactNode } from "react";
import styles from "./MarkTooltip.module.css";

interface Props {
  /** The mark itself. Receives the props that make it the tooltip's reference. */
  children: (
    props: Record<string, unknown> & { ref: (node: HTMLElement | null) => void },
  ) => ReactNode;
  label: string;
  detail?: string;
  meta: string;
  /** Drives the accent on the arrow and the top rule, matching the mark's meaning. */
  tone: string;
}

/**
 * What a mark on the timeline actually says.
 *
 * A mark is a coloured dot four pixels wide carrying a decision, a commitment or
 * a retrieved excerpt, and without this the only way to read one was a screen
 * reader. The label was always there for assistive technology; this makes it
 * available to everyone else too.
 *
 * Floating UI rather than hand-rolled positioning, and it earns the dependency:
 * the bands run the full width of the page, so a mark at 95% along needs its
 * tooltip flipped and shifted back into view. Collision handling is the whole
 * problem here, and doing it badly by hand is worse than importing it done well.
 *
 * `useFocus` alongside `useHover` is the point rather than a detail — a keyboard
 * user tabbing the timeline gets the same tooltip a mouse does.
 */
export function MarkTooltip({ children, label, detail, meta, tone }: Props) {
  const [open, setOpen] = useState(false);
  // State rather than a ref: the arrow middleware needs the element, and handing
  // it a ref means passing a mutable value through render, which React rightly
  // objects to. A callback ref writing into state gives the same element without
  // reading `.current` anywhere.
  const [arrowEl, setArrowEl] = useState<SVGSVGElement | null>(null);

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: "top",
    middleware: [
      offset(10),
      // Flip below when there is no room above — the first band sits near the top.
      flip({ padding: 8 }),
      // Slide back into view rather than hang off the edge.
      shift({ padding: 12 }),
      arrow({ element: arrowEl }),
    ],
  });

  const { getReferenceProps, getFloatingProps } = useInteractions([
    useHover(context, { delay: { open: 90, close: 0 }, move: false }),
    useFocus(context),
    useDismiss(context),
    useRole(context, { role: "tooltip" }),
  ]);

  // Honours prefers-reduced-motion on its own: the duration collapses rather than
  // the tooltip disappearing.
  const { isMounted, styles: transition } = useTransitionStyles(context, {
    duration: { open: 140, close: 80 },
    initial: { opacity: 0, transform: "translateY(4px) scale(0.97)" },
  });

  return (
    <>
      {children({ ref: refs.setReference, ...getReferenceProps() })}

      {isMounted && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            className={styles.layer}
            {...getFloatingProps()}
          >
            <div className={styles.tip} style={{ ...transition, borderTopColor: tone }}>
              <p className={styles.label}>{label}</p>
              {detail && <p className={styles.detail}>{detail}</p>}
              <p className={styles.meta}>{meta}</p>

              <FloatingArrow
                ref={setArrowEl}
                context={context}
                className={styles.arrow}
                width={12}
                height={6}
              />
            </div>
          </div>
        </FloatingPortal>
      )}
    </>
  );
}
