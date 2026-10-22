import argparse
import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=18866)
    args=parser.parse_args()
    uvicorn.run('historysys.api:app',host='127.0.0.1',port=args.port)
