import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import appConfig from "../../public/app-config.json";
import { configureApp } from "../lib/config.js";

configureApp(structuredClone(appConfig));

afterEach(cleanup);
