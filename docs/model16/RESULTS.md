# MODEL-16 bounded Generation 1 results

Retain MODEL-13 for now. The frozen challenger does not establish enough consistent independent evidence for replacement. Further development would require a newly authorized descendant generation; Generation 1 is closed to retuning.

All development comparisons use 2024–2025 Seed Points with deterministic physical-location-grouped nested validation and equal total fitting weight per location. Metrics below use one mean forecast/prediction pair per location; the JSON includes row-weighted error diagnostics, state results, fold results and calibration.

## Candidate comparison

| Candidate | State/status | Spearman | Kendall | Log RMSE | Level MAE | Top-quartile overlap | Stability |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean_model13_baseline | pooled | 0.4652 | 0.3267 | 0.1158 | 25941.5608 | 0.5000 | 0.6293 |
| clean_model13_baseline | MI | 0.2882 | 0.2058 | 0.1169 | 26337.4566 | 0.4615 | 0.6293 |
| clean_model13_baseline | WI | 0.7078 | 0.5238 | 0.1131 | 25017.8038 | 0.5000 | 0.6293 |
| ridge | pooled | 0.4909 | 0.3408 | 0.1102 | 25062.8274 | 0.4444 | 0.7441 |
| ridge | MI | 0.3808 | 0.2738 | 0.1055 | 23726.6330 | 0.4615 | 0.7441 |
| ridge | WI | 0.6753 | 0.4762 | 0.1206 | 28180.6144 | 0.3333 | 0.7441 |
| lasso | pooled | 0.4490 | 0.3159 | 0.1101 | 24715.8406 | 0.3889 | 0.5004 |
| lasso | MI | 0.2581 | 0.1837 | 0.1089 | 24910.1337 | 0.3077 | 0.5004 |
| lasso | WI | 0.7623 | 0.5619 | 0.1128 | 24262.4901 | 0.5000 | 0.5004 |
| elastic_net | pooled | 0.4590 | 0.3184 | 0.1089 | 24502.7630 | 0.3889 | 0.5250 |
| elastic_net | MI | 0.2827 | 0.1990 | 0.1074 | 24563.0138 | 0.3077 | 0.5250 |
| elastic_net | WI | 0.7390 | 0.5333 | 0.1123 | 24362.1779 | 0.5000 | 0.5250 |
| spline_ridge | pooled | 0.5033 | 0.3466 | 0.1173 | 25684.5122 | 0.3889 | 0.8201 |
| spline_ridge | MI | 0.3491 | 0.2381 | 0.1083 | 23988.2063 | 0.3846 | 0.8201 |
| spline_ridge | WI | 0.7273 | 0.5143 | 0.1358 | 29642.5594 | 0.3333 | 0.8201 |
| pca_ridge | pooled | 0.4451 | 0.3060 | 0.1120 | 24819.7217 | 0.4444 | 0.6806 |
| pca_ridge | MI | 0.2918 | 0.1939 | 0.1117 | 24557.7793 | 0.4615 | 0.6806 |
| pca_ridge | WI | 0.6987 | 0.4952 | 0.1128 | 25430.9208 | 0.3333 | 0.6806 |
| random_forest | pooled | 0.4737 | 0.3058 | 0.1157 | 26058.5148 | 0.4444 | 0.5667 |
| random_forest | MI | 0.3762 | 0.2451 | 0.1102 | 25657.7563 | 0.4615 | 0.5667 |
| random_forest | WI | 0.5424 | 0.3580 | 0.1278 | 26993.6180 | 0.5000 | 0.5667 |
| extra_trees | pooled | 0.4424 | 0.3101 | 0.1129 | 24450.3749 | 0.3333 | 0.6074 |
| extra_trees | MI | 0.3183 | 0.2177 | 0.1101 | 24729.8946 | 0.3846 | 0.6074 |
| extra_trees | WI | 0.7234 | 0.5238 | 0.1190 | 23798.1621 | 0.5000 | 0.6074 |
| gradient_boosting | pooled | 0.4112 | 0.2733 | 0.1156 | 25511.9795 | 0.4444 | 0.5970 |
| gradient_boosting | MI | 0.2456 | 0.1611 | 0.1121 | 25255.3912 | 0.4615 | 0.5970 |
| gradient_boosting | WI | 0.5736 | 0.3866 | 0.1234 | 26110.6857 | 0.5000 | 0.5970 |
| state_partial_pooling | pooled | 0.4797 | 0.3383 | 0.1104 | 24976.3894 | 0.3889 | 0.7172 |
| state_partial_pooling | MI | 0.3505 | 0.2585 | 0.1067 | 23969.4338 | 0.3846 | 0.7172 |
| state_partial_pooling | WI | 0.6974 | 0.4857 | 0.1185 | 27325.9524 | 0.5000 | 0.7172 |
| simple_log_ensemble | pooled | 0.4674 | 0.3168 | 0.1112 | 24951.6172 | 0.4444 | 0.6995 |
| simple_log_ensemble | MI | 0.3533 | 0.2432 | 0.1065 | 24218.7848 | 0.4615 | 0.6995 |
| simple_log_ensemble | WI | 0.7312 | 0.5048 | 0.1215 | 26661.5595 | 0.3333 | 0.6995 |
| family_remove__baseline_demographics | pooled | 0.4264 | 0.2903 | 0.1137 | 25978.5820 | 0.4444 | 0.7462 |
| family_remove__baseline_demographics | MI | 0.3284 | 0.2211 | 0.1076 | 24410.8147 | 0.4615 | 0.7462 |
| family_remove__baseline_demographics | WI | 0.5610 | 0.4000 | 0.1268 | 29636.7058 | 0.3333 | 0.7462 |
| family_add__business_context | pooled | 0.3616 | 0.2505 | 0.1111 | 24127.4299 | 0.3333 | 0.8016 |
| family_add__business_context | MI | 0.1763 | 0.1173 | 0.1105 | 24718.6181 | 0.3846 | 0.8016 |
| family_add__business_context | WI | 0.6818 | 0.4857 | 0.1126 | 22747.9907 | 0.5000 | 0.8016 |
| family_remove__business_context | pooled | 0.5025 | 0.3441 | 0.1097 | 24902.3598 | 0.4444 | 0.7512 |
| family_remove__business_context | MI | 0.3949 | 0.2789 | 0.1050 | 23633.9320 | 0.4615 | 0.7512 |
| family_remove__business_context | WI | 0.6870 | 0.4857 | 0.1200 | 27862.0247 | 0.3333 | 0.7512 |
| family_add__commuting | pooled | 0.3609 | 0.2497 | 0.1110 | 24176.8670 | 0.3333 | 0.8016 |
| family_add__commuting | MI | 0.1942 | 0.1310 | 0.1100 | 24746.5005 | 0.3846 | 0.8016 |
| family_add__commuting | WI | 0.6571 | 0.4667 | 0.1133 | 22847.7222 | 0.5000 | 0.8016 |
| family_remove__commuting | pooled | 0.4913 | 0.3416 | 0.1100 | 24966.7111 | 0.4444 | 0.7492 |
| family_remove__commuting | MI | 0.3790 | 0.2704 | 0.1054 | 23668.1447 | 0.4615 | 0.7492 |
| family_remove__commuting | WI | 0.6753 | 0.4762 | 0.1200 | 27996.6992 | 0.3333 | 0.7492 |
| family_add__commuting_flows | pooled | 0.3615 | 0.2513 | 0.1112 | 24347.8642 | 0.3333 | 0.7994 |
| family_add__commuting_flows | MI | 0.2057 | 0.1463 | 0.1096 | 24721.8967 | 0.3846 | 0.7994 |
| family_add__commuting_flows | WI | 0.6416 | 0.4476 | 0.1150 | 23475.1217 | 0.5000 | 0.7994 |
| family_remove__commuting_flows | pooled | 0.4875 | 0.3458 | 0.1097 | 24853.7992 | 0.3889 | 0.7478 |
| family_remove__commuting_flows | MI | 0.3661 | 0.2755 | 0.1059 | 23762.6348 | 0.4615 | 0.7478 |
| family_remove__commuting_flows | WI | 0.6896 | 0.4762 | 0.1181 | 27399.8495 | 0.5000 | 0.7478 |
| family_add__construction_permits | pooled | 0.4519 | 0.3168 | 0.1114 | 23964.9908 | 0.3889 | 0.7394 |
| family_add__construction_permits | MI | 0.3355 | 0.2296 | 0.1088 | 23924.1593 | 0.4615 | 0.7394 |
| family_add__construction_permits | WI | 0.6377 | 0.4381 | 0.1174 | 24060.2642 | 0.3333 | 0.7394 |
| family_remove__construction_permits | pooled | 0.4672 | 0.3259 | 0.1110 | 25141.6260 | 0.4444 | 0.7406 |
| family_remove__construction_permits | MI | 0.3269 | 0.2364 | 0.1071 | 24039.9731 | 0.4615 | 0.7406 |
| family_remove__construction_permits | WI | 0.6844 | 0.4952 | 0.1197 | 27712.1492 | 0.5000 | 0.7406 |
| family_add__county_business | pooled | 0.3616 | 0.2522 | 0.1112 | 24306.4621 | 0.3333 | 0.8031 |
| family_add__county_business | MI | 0.1894 | 0.1344 | 0.1102 | 24862.1152 | 0.3846 | 0.8031 |
| family_add__county_business | WI | 0.6649 | 0.4667 | 0.1135 | 23009.9381 | 0.5000 | 0.8031 |
| family_remove__county_business | pooled | 0.4910 | 0.3391 | 0.1103 | 25039.4495 | 0.4444 | 0.7444 |
| family_remove__county_business | MI | 0.3856 | 0.2721 | 0.1057 | 23752.4347 | 0.4615 | 0.7444 |
| family_remove__county_business | WI | 0.6649 | 0.4762 | 0.1202 | 28042.4840 | 0.3333 | 0.7444 |
| family_add__employment | pooled | 0.4401 | 0.3085 | 0.1082 | 23508.6793 | 0.3889 | 0.8119 |
| family_add__employment | MI | 0.2760 | 0.1871 | 0.1079 | 24043.5433 | 0.4615 | 0.8119 |
| family_add__employment | WI | 0.7377 | 0.5333 | 0.1091 | 22260.6632 | 0.6667 | 0.8119 |
| family_remove__employment | pooled | 0.4488 | 0.3110 | 0.1118 | 25398.3351 | 0.3889 | 0.7449 |
| family_remove__employment | MI | 0.3245 | 0.2398 | 0.1067 | 24083.6220 | 0.3846 | 0.7449 |
| family_remove__employment | WI | 0.6221 | 0.4286 | 0.1228 | 28465.9991 | 0.3333 | 0.7449 |
| family_add__food_access | pooled | 0.3778 | 0.2646 | 0.1115 | 24291.0414 | 0.3889 | 0.7878 |
| family_add__food_access | MI | 0.1904 | 0.1310 | 0.1100 | 24801.2176 | 0.3846 | 0.7878 |
| family_add__food_access | WI | 0.6766 | 0.4952 | 0.1148 | 23100.6303 | 0.5000 | 0.7878 |
| family_remove__food_access | pooled | 0.4996 | 0.3491 | 0.1090 | 24373.2136 | 0.3889 | 0.7607 |
| family_remove__food_access | MI | 0.3622 | 0.2568 | 0.1061 | 23730.5193 | 0.4615 | 0.7607 |
| family_remove__food_access | WI | 0.7286 | 0.5143 | 0.1154 | 25872.8336 | 0.5000 | 0.7607 |
| family_add__growth | pooled | 0.3873 | 0.2538 | 0.1108 | 24429.8860 | 0.3889 | 0.8018 |
| family_add__growth | MI | 0.2127 | 0.1361 | 0.1096 | 24689.2695 | 0.3846 | 0.8018 |
| family_add__growth | WI | 0.6338 | 0.4190 | 0.1137 | 23824.6578 | 0.5000 | 0.8018 |
| family_remove__growth | pooled | 0.4991 | 0.3474 | 0.1101 | 24896.0065 | 0.3889 | 0.7490 |
| family_remove__growth | MI | 0.3777 | 0.2704 | 0.1059 | 23817.5664 | 0.4615 | 0.7490 |
| family_remove__growth | WI | 0.7026 | 0.4952 | 0.1194 | 27412.3667 | 0.5000 | 0.7490 |
| family_add__household_economics | pooled | 0.3530 | 0.2414 | 0.1119 | 24301.1580 | 0.3333 | 0.7819 |
| family_add__household_economics | MI | 0.1729 | 0.1122 | 0.1113 | 24901.1736 | 0.3846 | 0.7819 |
| family_add__household_economics | WI | 0.6481 | 0.4476 | 0.1132 | 22901.1216 | 0.5000 | 0.7819 |
| family_remove__household_economics | pooled | 0.4980 | 0.3449 | 0.1093 | 24893.3788 | 0.4444 | 0.7611 |
| family_remove__household_economics | MI | 0.4002 | 0.2806 | 0.1044 | 23533.7727 | 0.4615 | 0.7611 |
| family_remove__household_economics | WI | 0.6701 | 0.4667 | 0.1200 | 28065.7930 | 0.3333 | 0.7611 |
| family_add__household_mass | pooled | 0.3622 | 0.2505 | 0.1109 | 24143.9583 | 0.3333 | 0.8094 |
| family_add__household_mass | MI | 0.1886 | 0.1241 | 0.1100 | 24716.1869 | 0.3846 | 0.8094 |
| family_add__household_mass | WI | 0.6597 | 0.4762 | 0.1130 | 22808.7580 | 0.5000 | 0.8094 |
| family_remove__household_mass | pooled | 0.4758 | 0.3259 | 0.1108 | 25147.7792 | 0.4444 | 0.7448 |
| family_remove__household_mass | MI | 0.3659 | 0.2619 | 0.1061 | 23853.6320 | 0.3846 | 0.7448 |
| family_remove__household_mass | WI | 0.6636 | 0.4476 | 0.1212 | 28167.4560 | 0.3333 | 0.7448 |
| family_add__housing_urban_form | pooled | 0.4031 | 0.2770 | 0.1100 | 24091.8094 | 0.3889 | 0.8109 |
| family_add__housing_urban_form | MI | 0.2382 | 0.1633 | 0.1095 | 24586.5400 | 0.3846 | 0.8109 |
| family_add__housing_urban_form | WI | 0.6987 | 0.4952 | 0.1112 | 22937.4378 | 0.5000 | 0.8109 |
| family_remove__housing_urban_form | pooled | 0.4818 | 0.3325 | 0.1106 | 25096.9967 | 0.3889 | 0.7407 |
| family_remove__housing_urban_form | MI | 0.3631 | 0.2585 | 0.1059 | 23779.6848 | 0.3846 | 0.7407 |
| family_remove__housing_urban_form | WI | 0.6870 | 0.4857 | 0.1210 | 28170.7246 | 0.3333 | 0.7407 |
| family_add__roads_urban_form | pooled | 0.4013 | 0.2778 | 0.1101 | 24164.4926 | 0.3889 | 0.8159 |
| family_add__roads_urban_form | MI | 0.2485 | 0.1752 | 0.1091 | 24360.5974 | 0.4615 | 0.8159 |
| family_add__roads_urban_form | WI | 0.6740 | 0.4762 | 0.1125 | 23706.9148 | 0.3333 | 0.8159 |
| family_remove__roads_urban_form | pooled | 0.4889 | 0.3366 | 0.1100 | 24928.6000 | 0.4444 | 0.7442 |
| family_remove__roads_urban_form | MI | 0.3684 | 0.2585 | 0.1057 | 23829.2325 | 0.4615 | 0.7442 |
| family_remove__roads_urban_form | WI | 0.7000 | 0.4952 | 0.1193 | 27493.7910 | 0.5000 | 0.7442 |
| family_add__transit_access | pooled | 0.3622 | 0.2505 | 0.1109 | 24143.9583 | 0.3333 | 0.8094 |
| family_add__transit_access | MI | 0.1886 | 0.1241 | 0.1100 | 24716.1869 | 0.3846 | 0.8094 |
| family_add__transit_access | WI | 0.6597 | 0.4762 | 0.1130 | 22808.7580 | 0.5000 | 0.8094 |
| family_remove__transit_access | pooled | 0.4909 | 0.3408 | 0.1102 | 25062.8274 | 0.4444 | 0.7441 |
| family_remove__transit_access | MI | 0.3808 | 0.2738 | 0.1055 | 23726.6330 | 0.4615 | 0.7441 |
| family_remove__transit_access | WI | 0.6753 | 0.4762 | 0.1206 | 28180.6144 | 0.3333 | 0.7441 |
| family_add__travel_access | pooled | 0.4134 | 0.2894 | 0.1104 | 24293.4645 | 0.3889 | 0.7998 |
| family_add__travel_access | MI | 0.2542 | 0.1837 | 0.1090 | 24477.1844 | 0.4615 | 0.7998 |
| family_add__travel_access | WI | 0.7286 | 0.4952 | 0.1138 | 23864.7850 | 0.6667 | 0.7998 |
| family_remove__travel_access | pooled | 0.4923 | 0.3416 | 0.1102 | 25030.9225 | 0.3889 | 0.7461 |
| family_remove__travel_access | MI | 0.3805 | 0.2721 | 0.1059 | 23818.4243 | 0.4615 | 0.7461 |
| family_remove__travel_access | WI | 0.6753 | 0.4762 | 0.1195 | 27860.0850 | 0.3333 | 0.7461 |
| baseline_terms_ridge | pooled | 0.3622 | 0.2505 | 0.1109 | 24143.9583 | 0.3333 | 0.8094 |
| baseline_terms_ridge | MI | 0.1886 | 0.1241 | 0.1100 | 24716.1869 | 0.3846 | 0.8094 |
| baseline_terms_ridge | WI | 0.6597 | 0.4762 | 0.1130 | 22808.7580 | 0.5000 | 0.8094 |

## Selection and sensitivity

Frozen baseline: `clean_model13_baseline`. Frozen challenger: `family_remove__food_access`.

- `ridge`: NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `lasso`: ANY_LOCATION_SENSITIVITY, LOW_FEATURE_STABILITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT.
- `elastic_net`: ANY_LOCATION_SENSITIVITY, LOW_FEATURE_STABILITY.
- `spline_ridge`: ANY_LOCATION_SENSITIVITY, MARKET_CONCENTRATION_SENSITIVITY, WI_DETERIORATION.
- `pca_ridge`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WORST_LOCATION_SENSITIVITY.
- `random_forest`: ANY_LOCATION_SENSITIVITY, LOW_FEATURE_STABILITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `extra_trees`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `gradient_boosting`: ANY_LOCATION_SENSITIVITY, IMPROVEMENT_NOT_REPEATABLE_ACROSS_FOLDS, LOW_FEATURE_STABILITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `state_partial_pooling`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT.
- `simple_log_ensemble`: ANY_LOCATION_SENSITIVITY, ENSEMBLE_NOT_BETTER_THAN_CONSTITUENTS, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_remove__baseline_demographics`: ANY_LOCATION_SENSITIVITY, IMPROVEMENT_NOT_REPEATABLE_ACROSS_FOLDS, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_add__business_context`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WORST_LOCATION_SENSITIVITY.
- `family_remove__business_context`: WI_DETERIORATION.
- `family_add__commuting`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__commuting`: WI_DETERIORATION.
- `family_add__commuting_flows`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__commuting_flows`: SOURCE_FAMILY_DEPENDENCE.
- `family_add__construction_permits`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_remove__construction_permits`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__county_business`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__county_business`: NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__employment`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT.
- `family_remove__employment`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__food_access`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__food_access`: cleared development gates.
- `family_add__growth`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__growth`: WI_DETERIORATION.
- `family_add__household_economics`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__household_economics`: WI_DETERIORATION.
- `family_add__household_mass`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__household_mass`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__housing_urban_form`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WORST_LOCATION_SENSITIVITY.
- `family_remove__housing_urban_form`: ANY_LOCATION_SENSITIVITY, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__roads_urban_form`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__roads_urban_form`: WI_DETERIORATION.
- `family_add__transit_access`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.
- `family_remove__transit_access`: NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `family_add__travel_access`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WORST_LOCATION_SENSITIVITY.
- `family_remove__travel_access`: NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION.
- `baseline_terms_ridge`: ANY_LOCATION_SENSITIVITY, MI_DETERIORATION, NO_MATERIAL_POOLED_IMPROVEMENT, WI_DETERIORATION, WORST_LOCATION_SENSITIVITY.

Worst-location omission diagnostics, aggregate sensitivity across all development locations, anonymous market-omission summaries, fold differences, and same-architecture family robustness results are retained in the accompanying public JSON. They describe fixed out-of-fold predictions and do not authorize target-conditioned refits.

## Source-family contribution

Addition error differences below zero favor adding a family. Removal error differences above zero show loss from removing a family. These are development diagnostics, not causal effects.

| Family | Operation | Reference | Pooled Spearman difference | Pooled log RMSE difference |
| --- | --- | --- | ---: | ---: |
| baseline_demographics | family_remove | ridge | -0.0646 | 0.0035 |
| business_context | family_add | baseline_terms_ridge | -0.0006 | 0.0002 |
| business_context | family_remove | ridge | 0.0116 | -0.0006 |
| commuting | family_add | baseline_terms_ridge | -0.0013 | 0.0001 |
| commuting | family_remove | ridge | 0.0004 | -0.0002 |
| commuting_flows | family_add | baseline_terms_ridge | -0.0007 | 0.0003 |
| commuting_flows | family_remove | ridge | -0.0034 | -0.0005 |
| construction_permits | family_add | baseline_terms_ridge | 0.0897 | 0.0005 |
| construction_permits | family_remove | ridge | -0.0238 | 0.0008 |
| county_business | family_add | baseline_terms_ridge | -0.0006 | 0.0003 |
| county_business | family_remove | ridge | 0.0000 | 0.0000 |
| employment | family_add | baseline_terms_ridge | 0.0779 | -0.0026 |
| employment | family_remove | ridge | -0.0422 | 0.0016 |
| food_access | family_add | baseline_terms_ridge | 0.0156 | 0.0006 |
| food_access | family_remove | ridge | 0.0087 | -0.0013 |
| growth | family_add | baseline_terms_ridge | 0.0251 | -0.0000 |
| growth | family_remove | ridge | 0.0082 | -0.0001 |
| household_economics | family_add | baseline_terms_ridge | -0.0092 | 0.0010 |
| household_economics | family_remove | ridge | 0.0071 | -0.0009 |
| household_mass | family_add | baseline_terms_ridge | 0.0000 | 0.0000 |
| household_mass | family_remove | ridge | -0.0152 | 0.0006 |
| housing_urban_form | family_add | baseline_terms_ridge | 0.0409 | -0.0009 |
| housing_urban_form | family_remove | ridge | -0.0091 | 0.0004 |
| roads_urban_form | family_add | baseline_terms_ridge | 0.0391 | -0.0008 |
| roads_urban_form | family_remove | ridge | -0.0020 | -0.0003 |
| transit_access | family_add | baseline_terms_ridge | 0.0000 | 0.0000 |
| transit_access | family_remove | ridge | 0.0000 | 0.0000 |
| travel_access | family_add | baseline_terms_ridge | 0.0512 | -0.0005 |
| travel_access | family_remove | ridge | 0.0013 | -0.0001 |

## One-time 2026 Seed Point evaluation

| Model | Subset | Domain | Observations | Locations | Spearman | Kendall | Log RMSE | Level MAE |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean_model13_baseline | all | pooled | 62 | 62 | 0.7091 | 0.5177 | 0.1085 | 25235.6972 |
| clean_model13_baseline | all | MI | 38 | 38 | 0.6785 | 0.4993 | 0.1092 | 25980.6478 |
| clean_model13_baseline | all | WI | 24 | 24 | 0.7765 | 0.6159 | 0.1075 | 24056.1921 |
| clean_model13_baseline | independent_development_location | pooled | 62 | 62 | 0.7091 | 0.5177 | 0.1085 | 25235.6972 |
| clean_model13_baseline | independent_development_location | MI | 38 | 38 | 0.6785 | 0.4993 | 0.1092 | 25980.6478 |
| clean_model13_baseline | independent_development_location | WI | 24 | 24 | 0.7765 | 0.6159 | 0.1075 | 24056.1921 |
| clean_model13_baseline | matched_development_location | Empty | 0 | 0 | — | — | — | — |
| family_remove__food_access | all | pooled | 62 | 62 | 0.7144 | 0.5283 | 0.1060 | 24995.4870 |
| family_remove__food_access | all | MI | 38 | 38 | 0.7138 | 0.5306 | 0.1071 | 25859.0980 |
| family_remove__food_access | all | WI | 24 | 24 | 0.7313 | 0.5362 | 0.1041 | 23628.1028 |
| family_remove__food_access | independent_development_location | pooled | 62 | 62 | 0.7144 | 0.5283 | 0.1060 | 24995.4870 |
| family_remove__food_access | independent_development_location | MI | 38 | 38 | 0.7138 | 0.5306 | 0.1071 | 25859.0980 |
| family_remove__food_access | independent_development_location | WI | 24 | 24 | 0.7313 | 0.5362 | 0.1041 | 23628.1028 |
| family_remove__food_access | matched_development_location | Empty | 0 | 0 | — | — | — | — |

## One-time pursued-site evaluation

| Model | Subset | Domain | Observations | Locations | Spearman | Kendall | Log RMSE | Level MAE |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean_model13_baseline | all | pooled | 36 | 36 | 0.5354 | 0.3694 | 0.1985 | 43476.9414 |
| clean_model13_baseline | all | MI | 17 | 17 | 0.1239 | 0.0741 | 0.2155 | 43728.6031 |
| clean_model13_baseline | all | WI | 19 | 19 | 0.7170 | 0.5513 | 0.1820 | 43251.7703 |
| clean_model13_baseline | independent_development_location | pooled | 36 | 36 | 0.5354 | 0.3694 | 0.1985 | 43476.9414 |
| clean_model13_baseline | independent_development_location | MI | 17 | 17 | 0.1239 | 0.0741 | 0.2155 | 43728.6031 |
| clean_model13_baseline | independent_development_location | WI | 19 | 19 | 0.7170 | 0.5513 | 0.1820 | 43251.7703 |
| clean_model13_baseline | matched_development_location | Empty | 0 | 0 | — | — | — | — |
| clean_model13_baseline | independent_of_all_seedpoints | pooled | 36 | 36 | 0.5354 | 0.3694 | 0.1985 | 43476.9414 |
| clean_model13_baseline | independent_of_all_seedpoints | MI | 17 | 17 | 0.1239 | 0.0741 | 0.2155 | 43728.6031 |
| clean_model13_baseline | independent_of_all_seedpoints | WI | 19 | 19 | 0.7170 | 0.5513 | 0.1820 | 43251.7703 |
| clean_model13_baseline | matched_seedpoint_location | Empty | 0 | 0 | — | — | — | — |
| family_remove__food_access | all | pooled | 36 | 36 | 0.4499 | 0.3631 | 0.1938 | 39778.8475 |
| family_remove__food_access | all | MI | 17 | 17 | 0.0049 | 0.0296 | 0.2291 | 45072.5841 |
| family_remove__food_access | all | WI | 19 | 19 | 0.6749 | 0.5279 | 0.1556 | 35042.3463 |
| family_remove__food_access | independent_development_location | pooled | 36 | 36 | 0.4499 | 0.3631 | 0.1938 | 39778.8475 |
| family_remove__food_access | independent_development_location | MI | 17 | 17 | 0.0049 | 0.0296 | 0.2291 | 45072.5841 |
| family_remove__food_access | independent_development_location | WI | 19 | 19 | 0.6749 | 0.5279 | 0.1556 | 35042.3463 |
| family_remove__food_access | matched_development_location | Empty | 0 | 0 | — | — | — | — |
| family_remove__food_access | independent_of_all_seedpoints | pooled | 36 | 36 | 0.4499 | 0.3631 | 0.1938 | 39778.8475 |
| family_remove__food_access | independent_of_all_seedpoints | MI | 17 | 17 | 0.0049 | 0.0296 | 0.2291 | 45072.5841 |
| family_remove__food_access | independent_of_all_seedpoints | WI | 19 | 19 | 0.6749 | 0.5279 | 0.1556 | 35042.3463 |
| family_remove__food_access | matched_seedpoint_location | Empty | 0 | 0 | — | — | — | — |

## Evidence accounting

| State | Year | Evidence class | Role | Observations | Locations |
| --- | ---: | --- | --- | ---: | ---: |
| MI | 2024 | SEED_POINT | development | 47 | 47 |
| MI | 2024 | SEED_POINT | excluded | 2 | 2 |
| MI | 2025 | PURSUED_SITE | pursued_test | 17 | 17 |
| MI | 2025 | SEED_POINT | development | 49 | 49 |
| MI | 2025 | SEED_POINT | excluded | 3 | 3 |
| MI | 2026 | SEED_POINT | temporal_test | 38 | 38 |
| WI | 2024 | SEED_POINT | development | 21 | 21 |
| WI | 2025 | PURSUED_SITE | pursued_test | 19 | 19 |
| WI | 2025 | SEED_POINT | development | 20 | 20 |
| WI | 2026 | SEED_POINT | temporal_test | 24 | 24 |

Counts are within each displayed group; locations repeated across years or evidence classes must not be summed as independent locations.

## Limits

- Public-data customer-geography proxy; no proprietary-model equivalence or production-readiness claim.
- Matched physical locations are not independent external evidence; temporal rank metrics do not measure within-location change.
- Development candidate selection is not independent confirmation; all preprocessing and tuning remained inside location-grouped nested validation.
- Parameters, exact memberships, predictions, source identities, protected hashes and local paths remain protected.
- Source vintages, coverage limits and fixed-snapshot structural features must be interpreted with the public source report.
