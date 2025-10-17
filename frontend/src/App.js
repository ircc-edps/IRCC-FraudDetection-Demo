import React, { useState } from "react";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import "tailwindcss/tailwind.css";

// Determine API base URL: prefer build-time env, fall back to sensible defaults
const API_BASE =
  process.env.REACT_APP_API_BASE ||
  (typeof window !== "undefined" && window.location.hostname.includes("azurewebsites.net")
    ? "https://dev-ircc-edocs-fraud-backend-web-app.azurewebsites.net"
    : "http://localhost:8080");

// Configuration options that can be customized per implementation
const CONFIG = {
  apiEndpoints: {
    upload: `${API_BASE}/upload`,
    status: `${API_BASE}/status`,
  },
  documentTypes: {
    supportedFormats: [".pdf"], // Add more formats as needed
    acceptString: ".pdf", // Accept string for file input
  },
  formTitle: "eDoc Fraud Detection",
  validatorDescription:
    "Submit application data and get AI-powered fraud detection",
  pollingIntervalMs: 2000,
};

const initialState = {
  isDocotored: null,
  recommendations: [],
  validFields: [],
  invalidFields: [],
  overlayImageUrl: null,
  tampered_chunks: [],
  response: null,
};

export default function FormValidator() {
  const [file, setFile] = useState(null);
  const [pending, setPending] = useState(false);
  const [state, setState] = useState(initialState);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setState(initialState);
  };
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setPending(true);

    console.log(
      "Starting file upload:",
      file.name,
      "Size:",
      file.size,
      "Type:",
      file.type
    );

    // Prepare form data
    const formData = new FormData();
    formData.append("file", file);
    console.log("FormData prepared with file");

    try {
      // Upload to blob storage using the configured upload endpoint
      console.log(
        `Sending POST request to ${CONFIG.apiEndpoints.upload} endpoint`
      );
      const res = await fetch(CONFIG.apiEndpoints.upload, {
        method: "POST",
        body: formData,
      });
      console.log("Received response:", res.status, res.statusText);

      // Log full response details
      const responseText = await res.text();
      console.log("Full response:", responseText);

      // Parse response if it's JSON
      let data;
      try {
        data = JSON.parse(responseText);
        console.log("Parsed response data:", data);
      } catch (e) {
        console.error("Response was not valid JSON:", e);
      }

      if (res.ok && data) {
        console.log("Upload successful, response data:", data);
        // Start polling for processing status
        checkProcessingStatus(data.filename);
      } else {
        console.error("Upload failed:", res.status, responseText);
        setState({
          isValid: false,
          recommendations: [
            `Error uploading file: ${res.status} ${res.statusText}. Details: ${responseText}`,
          ],
          validFields: [],
          invalidFields: [],
        });
        setPending(false);
      }
    } catch (error) {
      console.error("Exception during upload:", error);
      setState({
        isValid: false,
        recommendations: [`Exception during upload: ${error.message}`],
        validFields: [],
        invalidFields: [],
      });
      setPending(false);
    }
  };
  // Poll for processing status
  const checkProcessingStatus = async (filename) => {
    try {
      const statusUrl = `${CONFIG.apiEndpoints.status}/${filename}`;
      console.log(`Checking status at: ${statusUrl}`);
      const res = await fetch(statusUrl);
      const data = await res.json();
      console.log("Status check response:", data);

      if (data.ready && data.report) {
        // If processing is complete, parse the report
        let report;
        try {
          report =
            typeof data.report === "string"
              ? JSON.parse(data.report)
              : data.report;
          console.log("Parsed report:", report);

          // Transform the API-specific format to our UI format
          if (report.status === "success") {
            // Mark as valid only if there are no issues
            const isValid =
              report.tampered_chunks && report.tampered_chunks.length === 0;

            // Create recommendations from issues
            const recommendations = [];
            if (
              report.status === "success" &&
              (!report.tampered_chunks || report.tampered_chunks.length === 0)
            ) {
              recommendations.push(
                "Application was successfully processed with no issues found."
              );
            } else if (report.status === "success") {
              recommendations.push(
                "Application was successfully processed but fraudulent activity was detected."
              );
            } else {
              recommendations.push(
                `Application processing status: ${report.status}`
              );
            }

            // Add request ID as a recommendation for reference
            // if (report.request_id) {
            //   recommendations.push(`Reference ID: ${report.request_id}`);
            // }

            if (report.response?.explanation?.length > 0) {
              report.response.explanation.forEach((item) => {
                const { chunk, confidence, risk, reasoning } = item;
                recommendations.push(
                  `Chunk ${chunk}: [Risk: ${risk.toUpperCase()}, Confidence: ${confidence}/10] - ${reasoning}`
                );
              });
            }

            // Transform valid fields (fields not in issues)
            const validFields = [];
            if (report.status === "success") {
              validFields.push({
                field: "Document",
                reason: "Successfully processed and uploaded to storage.",
              });
            }

            // Transform issues to invalid fields
            const invalidFields = [];
            if (report.issues && report.issues.length > 0) {
              report.issues.forEach((issue) => {
                invalidFields.push({
                  field: issue.field || "Unknown field",
                  reason: `${issue.description}${
                    issue.action ? ` - Action required: ${issue.action}` : ""
                  }`,
                });
              });
            }

            const overlayImageUrl = report.overlay_image_url || null;

            const tampered_chunks = report.tampered_chunks || [];

            setState({
              isDocotored: isValid,
              recommendations,
              validFields,
              invalidFields,
              overlayImageUrl,
              tampered_chunks,
            });
          } else {
            // For any other status, handle as error
            setState({
              isValid: false,
              recommendations: [
                `Form processing completed with status: ${
                  report.status || "unknown"
                }`,
              ],
              validFields: [],
              invalidFields: [
                {
                  field: "Processing",
                  reason: "Form processing did not complete successfully.",
                },
              ],
            });
          }
        } catch (error) {
          console.warn(
            "Could not parse report as JSON, using default success values",
            error
          );
          // If the report isn't valid JSON but the status is ready, assume success
          setState({
            isValid: true,
            recommendations: ["File was successfully uploaded and processed."],
            validFields: [
              { field: "Document", reason: "Successfully processed." },
            ],
            invalidFields: [],
          });
        }
        setPending(false);
      } else if (data.ready) {
        // Report is ready but no report data, treat as success
        console.log("Status is ready but no report data, treating as success");
        setState({
          isValid: true,
          recommendations: ["File was successfully uploaded to blob storage."],
          validFields: [
            { field: "Document", reason: "Successfully uploaded to storage." },
          ],
          invalidFields: [],
        });
        setPending(false);
      } else {
        // If still processing, check again after the configured interval
        console.log(
          `File still processing, checking again in ${CONFIG.pollingIntervalMs}ms`
        );
        setTimeout(
          () => checkProcessingStatus(filename),
          CONFIG.pollingIntervalMs
        );
      }
    } catch (error) {
      console.error("Error checking processing status:", error);
      // Even if status check fails but we know upload succeeded, show success
      setState({
        isValid: true,
        recommendations: [
          "File was uploaded successfully, but status check failed.",
        ],
        validFields: [
          {
            field: "Upload",
            reason: "File was uploaded to storage successfully.",
          },
        ],
        invalidFields: [],
      });
      setPending(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-16">
      <div className="max-w-6xl mx-auto px-8">
        <div className="text-center mb-16">
          <h1 className="text-5xl font-extrabold text-gray-900 mb-4">
            {CONFIG.formTitle}
          </h1>
          <p className="text-2xl text-gray-700">
            {CONFIG.validatorDescription}
          </p>
          <p className="text-base text-gray-500 mt-4 italic">
            Note: AI validation is a helpful tool, but all results should be
            verified by a human reviewer.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Form Input Section */}
          <div className="bg-white rounded-2xl shadow-xl p-12 flex flex-col">
            <div className="mb-8">
              <h2 className="text-3xl font-bold text-gray-900">
                Upload Form Data
              </h2>
            </div>
            <form
              onSubmit={handleSubmit}
              className="space-y-8 flex-1 flex flex-col"
            >
              <div className="border-4 border-dashed border-gray-300 rounded-2xl p-12 text-center hover:border-gray-400 transition-colors">
                <div className="space-y-8">
                  <div>
                    <label htmlFor="file" className="cursor-pointer">
                      <span className="text-2xl font-semibold text-gray-900">
                        Upload your form data
                      </span>
                      <p className="text-lg text-gray-500 mt-2">
                        {CONFIG.documentTypes.supportedFormats.join(", ")} files
                        supported
                      </p>
                    </label>
                    <input
                      id="file"
                      name="file"
                      type="file"
                      accept={CONFIG.documentTypes.acceptString}
                      className="hidden"
                      required
                      onChange={handleFileChange}
                    />
                    {file && (
                      <p className="mt-4 text-green-700 text-lg font-medium">
                        {file.name}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    className="mt-4 px-8 py-4 bg-blue-600 text-white rounded-xl text-xl font-bold hover:bg-blue-700 transition"
                    onClick={() => document.getElementById("file").click()}
                  >
                    Upload
                  </button>
                </div>
              </div>

              <div className="text-lg text-gray-500 space-y-2">
                <p>
                  <strong>Supported formats:</strong>
                </p>
                {CONFIG.documentTypes.supportedFormats.map((format, index) => (
                  <p key={index}>• {format.replace(".", "").toUpperCase()}</p>
                ))}
              </div>

              <button
                type="submit"
                disabled={pending}
                className="w-full bg-black text-white py-4 rounded-xl text-2xl font-bold hover:bg-gray-900 transition"
              >
                {pending ? "Validating File..." : "Validate Form Data"}
              </button>
            </form>
          </div>

          {/* Results Section */}
          <div className="bg-white rounded-2xl shadow-xl p-12 flex flex-col">
            <div className="mb-8">
              <h2 className="text-3xl font-bold text-gray-900">
                Detection Results
              </h2>
            </div>
            <div className="flex-1">
              {state.isDocotored === null && !pending && (
                <div className="text-center text-gray-500 py-16">
                  <AlertTriangle className="mx-auto h-20 w-20 mb-8 opacity-50" />
                  <p className="text-2xl">
                    Submit the form to see AI Fraud Detection results
                  </p>
                </div>
              )}

              {pending && (
                <div className="text-center text-blue-600 py-16">
                  <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto mb-8"></div>
                  <p className="text-2xl">AI is analyzing your document...</p>
                </div>
              )}

              {state.isDocotored !== null && !pending && (
                <div className="space-y-10">
                  {/* Overall Status */}
                  <div
                    className={`border ${
                      state.isDocotored
                        ? "border-green-200 bg-green-50"
                        : "border-red-200 bg-red-50"
                    } rounded-xl p-8`}
                  >
                    <div className="flex items-center">
                      {state.isDocotored ? (
                        <CheckCircle className="h-8 w-8 text-green-600 mr-4" />
                      ) : (
                        <XCircle className="h-8 w-8 text-red-600 mr-4" />
                      )}
                      <span
                        className={`text-2xl font-bold ${
                          state.isDocotored ? "text-green-800" : "text-red-800"
                        }`}
                      >
                        {state.tampered_chunks && state.tampered_chunks.length === 0
                          ? "No fraud detected!"
                          : "Fraud detected!"}
                      </span>
                      <span
                        className={`text-2xl font-bold ${
                          state.isDocotored ? "text-green-800" : "text-red-800"
                        }`}
                      ></span>
                    </div>
                  </div>
                  {/* Valid Fields */}
                  {/* {state.validFields.length > 0 && (
                    <div>
                      <h3 className="text-2xl font-bold text-green-700 mb-4 flex items-center">
                        <CheckCircle className="h-8 w-8 mr-4" />
                        Valid Fields
                      </h3>
                      <div className="space-y-4">
                        {state.validFields.map((field, index) => (
                          <div
                            key={index}
                            className="bg-green-50 border border-green-200 rounded-xl p-6"
                          >
                            <p className="text-green-800 font-bold text-lg">
                              {field.field}
                            </p>
                            <p className="text-green-600 text-base mt-2">
                              {field.reason}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )} */}
                  {state.overlayImageUrl && (
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-8 mt-10">
                      <h3 className="text-2xl font-bold text-gray-900 mb-4">
                        Heatmap Overlay
                      </h3>
                      <img
                        src={state.overlayImageUrl}
                        alt="Fraud Detection Heatmap Overlay"
                        className="mx-auto max-w-full rounded-xl shadow-lg"
                      />
                    </div>
                  )}
                  {/* AI Recommendations */}
                  {state.recommendations.length > 0 && (
                    <div>
                      <h3 className="text-2xl font-bold text-blue-700 mb-4 flex items-center">
                        <AlertTriangle className="h-8 w-8 mr-4" />
                        Recommendations
                      </h3>
                      <div className="space-y-4">
                        {state.recommendations.map((recommendation, index) => (
                          <div
                            key={index}
                            className="bg-blue-50 border border-blue-200 rounded-xl p-6"
                          >
                            <p className="text-blue-800 text-lg">
                              {recommendation}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
