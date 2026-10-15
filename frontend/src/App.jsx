import { Routes, Route } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Apply from "./pages/Apply.jsx";
import NotFound from "./pages/NotFound.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/apply" element={<Apply />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
