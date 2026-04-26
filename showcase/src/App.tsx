import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { FilmPage } from "./pages/FilmPage";
import "./app.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/:slug" element={<FilmPage />} />
      </Routes>
    </BrowserRouter>
  );
}
