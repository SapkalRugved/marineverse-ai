\# Copernicus Ocean Data Ingestion



\## Purpose



This pipeline retrieves near-real-time modelled ocean conditions for

the Indian marine region, transforms the gridded data into a unified

record format, and bulk-loads valid records into PostgreSQL/PostGIS.



The pipeline provides:



\- Surface eastward and northward ocean currents

\- Calculated current speed and direction

\- Sea-surface temperature

\- Significant wave height

\- Wave-from direction

\- Mean wave period



Copernicus Marine provides numerical model analysis and forecast data.

It is not a live buoy or direct sensor observation source.



\## Data source



Source:



```text

copernicus-marine



\## Individual pipeline stages



Retrieve raw data:



```powershell

python -m backend.marine\_data.ocean.retrieve\_copernicus\_ocean





Confirm no unsafe placeholder remains:



```powershell

Select-String `

&#x20;   -Path docs\\ocean-ingestion.md `

&#x20;   -Pattern "<manifest-file>"	

