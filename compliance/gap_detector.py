def detect_gaps(match_results, threshold=0.6):

    missing = []
    present = []

    for item in match_results:

        if item["score"] < threshold:
            missing.append(item["clause"])
        else:
            present.append(item["clause"])

    return present, missing