"use client";
import dynamic from "next/dynamic";

const PathMap = dynamic(() => import("@/components/PathMap"), { ssr: false });

export default function Home() {
return <PathMap />;
}
