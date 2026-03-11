import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Builds } from "./pages/Builds";
import { BuildDetail } from "./pages/BuildDetail";
import { Devices } from "./pages/Devices";
import { Profiles } from "./pages/Profiles";

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/builds" element={<Builds />} />
          <Route path="/builds/:uuid" element={<BuildDetail />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/profiles" element={<Profiles />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
