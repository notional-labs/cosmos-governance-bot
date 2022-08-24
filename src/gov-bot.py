#!/usr/bin/python3

import json
import os
import schedule
import requests
import time

# from _ChainApis import chainAPIs, customExplorerLinks, DAOs
from pyibc_api import get_chain, CHAIN_APIS, CUSTOM_EXPLORER_LINKS, PAGES, DAOs, REST_ENDPOINTS # get_dao?

# Don't touch below --------------------------------------------------
proposals = {}
IS_FIRST_RUN = False

if not os.path.isfile("secrets.json"):
    print("\nsecrets.json not found, please create it like so:")
    print("cp secrets.example.json secrets.json\n")
    exit()

PREFIX="COSMOSGOV"

with open('secrets.json', 'r') as f:
    secrets = json.load(f)
    IN_PRODUCTION = secrets['IN_PRODUCTION']
    explorer = secrets['EXPLORER_DEFAULT'] # ping, mintscan, keplr
    USE_CUSTOM_LINKS = secrets['USE_CUSTOM_LINKS']
    SCHEDULE_SECONDS = 60 * int(secrets['MINUTES_BETWEEN_RUNNABLE'])
    LOG_RUNS = secrets['LOG_RUNS']    
    TICKERS_TO_ANNOUNCE = secrets.get('TICKERS_TO_ANNOUNCE', [])
    TICKERS_TO_IGNORE = secrets.get('TICKERS_TO_IGNORE', [])

    filename = secrets['FILENAME']
    
# Loads normal proposals (ticker -> id) dict
def load_proposals_from_file() -> dict:
    global proposals
    with open(filename, 'r') as f:
        proposals = json.load(f)       
        print(proposals)
    return proposals

def save_proposals() -> None:
    if len(proposals) > 0:
        with open(filename, 'w') as f:
            json.dump(proposals, f)

def update_proposal_value(ticker: str, newPropNumber: int):
    global proposals
    proposals[ticker] = newPropNumber
    save_proposals()

    # print(data)
    # https://discord.com/developers/docs/topics/gateway#thread-create

def get_explorer_link(ticker, propId):
    if USE_CUSTOM_LINKS and ticker in CUSTOM_EXPLORER_LINKS:
        return f"{CUSTOM_EXPLORER_LINKS[ticker]}/{PAGES[ticker]['gov_page'].replace('{id}', str(propId))}"

    # pingpub, mintscan, keplr
    # possibleExplorers = chainAPIs[ticker][1]
    chain_info = get_chain(ticker)
    possibleExplorers = chain_info['explorers']

    explorerToUse = explorer
    if explorerToUse not in possibleExplorers: # If it doesn't have a mintscan, default to ping.pub (index 0)
        explorerToUse = list(possibleExplorers.keys())[0]

    url = f"{chain_info['explorers'][explorerToUse]}/{PAGES[explorerToUse]['gov_page'].replace('{id}', str(propId))}"
    # print('get_explorer_link', url)
    return url

# This is so messy, make this more OOP related
def post_update(ticker, propID, title, description="", isDAO=False, DAOVoteLink=""):
    chainExploreLink = DAOVoteLink
    if isDAO == False:
        chainExploreLink = get_explorer_link(ticker, propID)

    message = f"${str(ticker).upper()} | Proposal #{propID} | VOTING | {title} | {chainExploreLink}"
    print(message)

    
    
def getAllProposals(ticker) -> list:
    # Makes request to API & gets JSON reply in form of a list
    props = []
    
    try:
        # link = chainAPIs[ticker][0]
        link = get_chain(ticker)['rest_root'] + "/" + REST_ENDPOINTS['proposals']
        response = requests.get(link, headers={
            'accept': 'application/json', 
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'}, 
            params={'proposal_status': '2'}) # 2 = voting period
        # print(response.url)
        props = response.json()['proposals']
    except Exception as e:
        print(f"Issue with request to {ticker}: {e}")
    return props

def checkIfNewestProposalIDIsGreaterThanLastTweet(ticker):
    # get our last tweeted proposal ID (that was in voting period), if it exists
    # if not, 0 is the value so we search through all proposals
    lastPropID = 0
    if ticker in proposals:
        lastPropID = int(proposals[ticker])

    # gets JSON list of all proposals
    props = getAllProposals(ticker)
    if len(props) == 0:
        return

    # loop through out last stored voted prop ID & newest proposal ID
    for prop in props:
        current_prop_id = int(prop['proposal_id'])

        # If this is a new proposal which is not the last one we tweeted for
        if current_prop_id > lastPropID:   
            print(f"Newest prop ID {current_prop_id} > last prop ID: {lastPropID}")
            
            if IS_FIRST_RUN or IN_PRODUCTION:      
                # save to proposals dict & to file (so we don't post again), unless its the first run                                 
                update_proposal_value(ticker, current_prop_id)
            else:
                print("Not in production, not writing to file.")

            post_update(
                ticker=ticker,
                propID=current_prop_id, 
                title=prop['content']['title'], 
                description=prop['content']['description'], # for discord embeds
            )

def logRun():
    if LOG_RUNS:
        with open("logs.txt", 'a') as flog:
            flog.write(str(time.ctime() + "\n"))

def runChecks():   
    print("Running checks...") 
    for chain in CHAIN_APIS.keys():
        try:
            if  len(TICKERS_TO_ANNOUNCE) > 0 and chain not in TICKERS_TO_ANNOUNCE:
                continue
            if len(TICKERS_TO_IGNORE) > 0 and chain in TICKERS_TO_IGNORE:
                # print(f"Ignoring {chain} as it is in the ignore list.")
                continue # ignore chains like terra we don't want to announce

            checkIfNewestProposalIDIsGreaterThanLastTweet(chain)
        except Exception as e:
            print(f"{chain} checkProp failed: {e}")

    logRun()
    print(f"All chains checked {time.ctime()}, waiting")


def updateChainsToNewestProposalsIfThisIsTheFirstTimeRunning():
    global IN_PRODUCTION, IS_FIRST_RUN
    '''
    Updates JSON file to the newest proposals provided this is the first time running
    '''
    if os.path.exists(filename):
        print(f"{filename} exists, not first run")
        return

    IS_FIRST_RUN = True
    if IN_PRODUCTION:
        IN_PRODUCTION = False
        
    print("Updating chains to newest values since you have not run this before, these will not be posted")
    runChecks()
    save_proposals()
    print("Run this again now, chains have been populated")
    exit(0)

if __name__ == "__main__":        

    updateChainsToNewestProposalsIfThisIsTheFirstTimeRunning()

    load_proposals_from_file()    

    # informs user & setups of length of time between runs
    if IN_PRODUCTION:        
        print("[!] BOT IS RUNNING IN PRODUCTION MODE!!!!!!!!!!!!!!!!!!")
        time.sleep(5)

        output = "[!] Running "
        if TICKERS_TO_ANNOUNCE == []:
            output += "all in 2 seconds"
        else:
            output += f"{TICKERS_TO_ANNOUNCE} in 2 seconds"
        print(output)
        time.sleep(2)
    else:
        SCHEDULE_SECONDS = 3
        print("Bot is in test mode...")

    runChecks()

    # If user does not use a crontab, this can be run in a screen/daemon session
    schedule.every(SCHEDULE_SECONDS).seconds.do(runChecks)  
    while True:
        print("Running runnable then waiting...")
        schedule.run_pending()
        time.sleep(SCHEDULE_SECONDS)
            

    
