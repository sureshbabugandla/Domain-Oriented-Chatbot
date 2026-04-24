import { ChatPage } from "@/pages/ChatPage";
import { AuthPage } from "@/pages/AuthPage";
import { useStore } from "@/lib/store";

export default function App() {
  const authStatus = useStore((s) => s.authStatus);
  return authStatus === "signed_in" ? <ChatPage /> : <AuthPage />;
}
